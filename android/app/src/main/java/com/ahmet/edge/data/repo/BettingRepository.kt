package com.ahmet.edge.data.repo

import com.ahmet.edge.data.local.*
import com.ahmet.edge.domain.model.*
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.sqrt

@Singleton
class BettingRepository @Inject constructor(
    private val betDao: BetDao,
    private val bankrollDao: BankrollDao,
    private val oddsDao: OddsDao
) {
    fun observeBets(): Flow<List<Bet>> = betDao.observeAll().map { it.map(BetEntity::toDomain) }

    fun observeBankroll(): Flow<Bankroll> =
        combine(bankrollDao.observe(), betDao.observeOpenExposure()) { state, exposure ->
            val s = state ?: BankrollEntity(1, 1000.0, 1000.0, 1000.0, Instant.now().epochSecond)
            Bankroll(s.current, s.starting, exposure, s.peak)
        }

    fun observePerformance(): Flow<List<MarketPerformance>> = betDao.observeByMarket()

    /**
     * Her tahmin kaydedilir — oynansın ya da oynanmasın (madde 94).
     * Oynanmayanlar "kağıt üstünde" kayıt olur; model denetimi onlarsız eksik kalır.
     */
    suspend fun record(bet: Bet, bankrollBefore: Double) = betDao.insert(
        BetEntity(
            matchId = bet.matchId, matchLabel = bet.matchLabel, market = bet.market,
            selection = bet.selection, modelProb = bet.modelProb,
            takenPrice = bet.takenPrice, stake = bet.stake,
            placedAtEpoch = bet.placedAt.epochSecond, closingPrice = null,
            outcome = BetOutcome.OPEN.name, pnl = null,
            wasPlaced = bet.wasPlaced, bankrollBefore = bankrollBefore
        )
    )

    fun observeRecentOutcomes(): Flow<List<String>> = betDao.observeRecentOutcomes()

    fun observeAverageStake(): Flow<Double> =
        betDao.observeAverageStake().map { it ?: 0.0 }

    /**
     * Sonuçlandırma. Üç iş birden yapılır:
     *  1. Kâr/zarar hesaplanır
     *  2. Kapanış oranı yakalanmışsa yazılır — CLV ancak bundan sonra ölçülebilir
     *  3. Kasa güncellenir ve zirve yeniden hesaplanır (drawdown için)
     *
     * Kağıt üstü kayıtlar (wasPlaced = false) kasayı ETKİLEMEZ ama
     * CLV istatistiğine girer — modelin karnesi onlarsız eksiktir.
     */
    suspend fun settle(betId: Long, outcome: BetOutcome) {
        val bet = betDao.byId(betId) ?: return
        if (bet.outcome != BetOutcome.OPEN.name) return

        val pnl = when (outcome) {
            BetOutcome.WIN -> bet.stake * (bet.takenPrice - 1.0)
            BetOutcome.LOSE -> -bet.stake
            BetOutcome.PUSH, BetOutcome.VOID, BetOutcome.OPEN -> 0.0
        }

        val closing = oddsDao.closingLines(bet.matchId)
            .firstOrNull { it.selection == bet.selection && it.market == bet.market }
            ?.price

        betDao.settle(betId, outcome.name, pnl, closing)

        if (bet.wasPlaced && pnl != 0.0) {
            val state = bankrollDao.observe().first()
                ?: BankrollEntity(1, 1000.0, 1000.0, 1000.0, Instant.now().epochSecond)
            val next = state.current + pnl
            bankrollDao.upsert(
                state.copy(
                    current = next,
                    peak = maxOf(state.peak, next),
                    updatedAtEpoch = Instant.now().epochSecond
                )
            )
        }
    }

    /** Maç başladığında kapanış oranını geriye dönük doldurur. */
    suspend fun captureClosingLines(matchId: Long) {
        oddsDao.closingLines(matchId).forEach {
            betDao.fillClosing(matchId, it.selection, it.price)
        }
    }

    suspend fun setBankroll(starting: Double) = bankrollDao.upsert(
        BankrollEntity(1, starting, starting, starting, Instant.now().epochSecond)
    )
}

/** CLV özeti (madde 77, 98, 99). Kâr değil, bu ölçü sistemin çalışıp çalışmadığını söyler. */
data class ClvSummary(
    val n: Int, val meanClv: Double, val beatCloseRate: Double,
    val roi: Double, val isSignificant: Boolean, val stdErr: Double
) {
    val verdict: String get() = when {
        n < 30 -> "Henüz karar için yeterli örneklem yok. En az 200 bahis gerekir."
        !isSignificant && meanClv > 0 -> "CLV pozitif ama istatistiksel olarak anlamlı değil. Devam et ve ölçmeye devam et."
        isSignificant && meanClv > 0 -> "Kapanış oranını tutarlı biçimde yeniyorsun. Sistem çalışıyor."
        meanClv <= 0 -> "Kapanış oranının altında kalıyorsun. Kâr ettiysen bile bu şanstır."
        else -> ""
    }
}

fun List<Bet>.clvSummary(): ClvSummary {
    val withClosing = filter { it.closingPrice != null }
    if (withClosing.isEmpty()) return ClvSummary(0, 0.0, 0.0, 0.0, false, 0.0)
    val clv = withClosing.map { it.clvPct!! }
    val mean = clv.average()
    val sd = if (clv.size > 1)
        sqrt(clv.sumOf { (it - mean) * (it - mean) } / (clv.size - 1)) else 0.0
    val se = if (clv.size > 1) sd / sqrt(clv.size.toDouble()) else 0.0
    val staked = withClosing.sumOf { it.stake }
    val pnl = withClosing.sumOf { it.pnl ?: 0.0 }
    return ClvSummary(
        n = clv.size, meanClv = mean,
        beatCloseRate = clv.count { it > 0 } / clv.size.toDouble(),
        roi = if (staked > 0) pnl / staked else 0.0,
        isSignificant = clv.size > 30 && mean > 2 * se, stdErr = se
    )
}

private fun BetEntity.toDomain() = Bet(
    id, matchId, matchLabel, market, selection, modelProb, takenPrice, stake,
    Instant.ofEpochSecond(placedAtEpoch), closingPrice,
    BetOutcome.valueOf(outcome), pnl, wasPlaced
)

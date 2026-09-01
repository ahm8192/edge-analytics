package com.ahmet.edge.domain.model

import java.time.Instant

data class League(
    val id: Long, val name: String, val country: String,
    val tier: Int, val dataQuality: Double
)

data class Team(val id: Long, val name: String, val shortName: String, val crestUrl: String?)

data class Match(
    val id: Long,
    val league: League,
    val home: Team,
    val away: Team,
    val kickoff: Instant,
    val status: MatchStatus,
    val homeGoals: Int? = null,
    val awayGoals: Int? = null,
    /** Modelin ürettiği gol beklentileri — skor matrisi bunlardan kurulur. */
    val lambdaHome: Double? = null,
    val lambdaAway: Double? = null,
    val rho: Double = -0.03,
    /** Örneklem ve veri kalitesinden türeyen güven. Kelly'yi ölçekler. */
    val modelConfidence: Double = 1.0,
    val bestEdgePct: Double? = null,
    val hasValue: Boolean = false,
    /** Sunucudan gelen kalibre olasılıklar (null ise cihazda hesaplanır). */
    val pHome: Double? = null,
    val pDraw: Double? = null,
    val pAway: Double? = null,
    val pOver25: Double? = null,
    val pBtts: Double? = null
)

enum class MatchStatus { SCHEDULED, LIVE, FINISHED, POSTPONED }

data class OddsQuote(
    val bookmaker: String,
    val market: String,
    val line: Double?,
    val prices: Map<String, Double>,
    val capturedAt: Instant,
    val isClosing: Boolean = false,
    val isSharp: Boolean = false
)

data class OddsPoint(val at: Instant, val selection: String, val price: Double)

data class ContextFactor(
    val label: String,
    val value: String,
    /** Gol beklentisine etkisi. Pozitif = gol artırıcı. */
    val impact: Double,
    val note: String? = null
)

data class Bet(
    val id: Long = 0,
    val matchId: Long,
    val matchLabel: String,
    val market: String,
    val selection: String,
    val modelProb: Double,
    val takenPrice: Double,
    val stake: Double,
    val placedAt: Instant,
    val closingPrice: Double? = null,
    val outcome: BetOutcome = BetOutcome.OPEN,
    val pnl: Double? = null,
    val wasPlaced: Boolean = true
) {
    val clvPct: Double? get() = closingPrice?.let { takenPrice / it - 1.0 }
}

enum class BetOutcome { OPEN, WIN, LOSE, PUSH, VOID }

data class Bankroll(
    val current: Double,
    val starting: Double,
    val openExposure: Double,
    val peak: Double
) {
    val pnl get() = current - starting
    val roi get() = if (starting > 0) pnl / starting else 0.0
    val drawdown get() = if (peak > 0) (peak - current) / peak else 0.0
}

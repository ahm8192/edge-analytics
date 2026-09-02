package com.ahmet.edge.data.repo

import com.ahmet.edge.core.AppError
import com.ahmet.edge.data.local.*
import com.ahmet.edge.data.remote.EdgeApi
import com.ahmet.edge.domain.model.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.json.Json
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Tek doğruluk kaynağı Room. Ağ sadece tazeler.
 * Böylece uçak modunda da uygulama çalışır — analiz zaten cihazda hesaplanıyor.
 */
@Singleton
class MatchRepository @Inject constructor(
    private val api: EdgeApi,
    private val matchDao: MatchDao,
    private val oddsDao: OddsDao,
    private val contextDao: ContextDao
) {

    fun observeWindow(from: Instant, to: Instant): Flow<List<Match>> =
        matchDao.observeWindow(from.epochSecond, to.epochSecond)
            .map { rows -> rows.mapNotNull { it.toDomain() } }

    fun observeValueBoard(): Flow<List<Match>> =
        matchDao.observeValueBoard(Instant.now().epochSecond).map { it.mapNotNull { r -> r.toDomain() } }

    /** Önümüzdeki maçlar — "model leanları" tablosu için (value şartı yok). */
    fun observeUpcoming(days: Long = 10): Flow<List<Match>> {
        val now = Instant.now()
        return matchDao.observeWindow(now.epochSecond, now.plusSeconds(days * 86400).epochSecond)
            .map { it.mapNotNull { r -> r.toDomain() } }
    }

    fun observeMatch(id: Long): Flow<Match?> =
        matchDao.observeOne(id).map { it?.toDomain() }

    fun observeOdds(matchId: Long, market: String): Flow<Map<String, Double>> =
        oddsDao.observeLatest(matchId, market)
            .map { rows -> rows.associate { it.selection to it.price } }

    fun observeMovement(matchId: Long, market: String, sel: String): Flow<List<OddsPoint>> =
        oddsDao.observeMovement(matchId, market, sel).map { rows ->
            rows.map { OddsPoint(Instant.ofEpochSecond(it.capturedEpoch), it.selection, it.price) }
        }

    fun observeContext(matchId: Long): Flow<List<ContextFactor>> =
        contextDao.observe(matchId).map { rows ->
            rows.map { ContextFactor(it.label, it.value, it.impact, it.note) }
        }

    suspend fun refreshWindow(from: Instant, to: Instant): AppError? = try {
        android.util.Log.i("EDGE", "refreshWindow basladi from=$from to=$to base=${com.ahmet.edge.BuildConfig.API_BASE}")
        // Render ucretsiz plan soguk baslangicta 30-60 sn uyanabilir; birkac kez dene.
        var resp = api.matches(from.toString(), to.toString())
        var tries = 0
        while (!resp.isSuccessful && resp.code() >= 500 && tries < 3) {
            tries++
            delay(5000L * tries)
            resp = api.matches(from.toString(), to.toString())
        }
        android.util.Log.i("EDGE", "refreshWindow yanit code=${resp.code()} ok=${resp.isSuccessful}")
        if (resp.isSuccessful) {
            val body = resp.body()!!
            android.util.Log.i("EDGE", "refreshWindow body matches=${body.matches.size} leagues=${body.leagues.size} teams=${body.teams.size}")
            val now = Instant.now().epochSecond
            matchDao.upsertLeagues(body.leagues.map {
                LeagueEntity(it.id, it.name, it.country, it.tier, it.dataQuality, it.strengthCoef)
            })
            matchDao.upsertTeams(body.teams.map {
                TeamEntity(it.id, it.name, it.shortName, it.crestUrl)
            })
            // Yakın maçlarda Pinnacle 1X2 -> odds tablosu (edge/Kelly otomatik hesaplansın)
            val now2 = Instant.now().epochSecond
            body.matches.forEach { m ->
                if (m.pinnacleHome != null && m.pinnacleDraw != null && m.pinnacleAway != null) {
                    runCatching {
                        oddsDao.upsert(listOf(
                            OddsEntity(m.id, "PINNACLE", "1X2", null, "HOME", m.pinnacleHome, now2, false, true),
                            OddsEntity(m.id, "PINNACLE", "1X2", null, "DRAW", m.pinnacleDraw, now2, false, true),
                            OddsEntity(m.id, "PINNACLE", "1X2", null, "AWAY", m.pinnacleAway, now2, false, true),
                        ))
                    }
                }
            }
            matchDao.upsert(body.matches.map { m ->
                MatchEntity(m.id, m.leagueId, m.homeTeamId, m.awayTeamId,
                    Instant.parse(m.kickoff).epochSecond, m.status, m.homeGoals, m.awayGoals,
                    m.lambdaHome, m.lambdaAway, m.rho, m.modelConfidence,
                    m.bestEdgePct, m.hasValue,
                    m.pHome, m.pDraw, m.pAway, m.pOver25, m.pBtts, m.minute, now)
            })
            android.util.Log.i("EDGE", "refreshWindow DB yazildi, tamam")
            null
        } else mapError(resp.code(), resp.errorBody()?.string())
    } catch (e: Exception) {
        android.util.Log.e("EDGE", "refreshWindow HATA: ${e.javaClass.name}: ${e.message}", e)
        AppError.Offline
    }

    suspend fun refreshAnalysis(matchId: Long): AppError? = try {
        val resp = api.analysis(matchId)
        if (resp.isSuccessful) {
            val a = resp.body()!!
            contextDao.upsert(a.contextFactors.map {
                ContextFactorEntity(matchId, it.label, it.value, it.impact, it.note)
            })
            null
        } else mapError(resp.code(), resp.errorBody()?.string())
    } catch (e: Exception) { AppError.Offline }

    suspend fun refreshOdds(matchId: Long, market: String = "1X2"): AppError? = try {
        val resp = api.odds(matchId, market)
        if (resp.isSuccessful) {
            oddsDao.upsert(resp.body()!!.quotes.flatMap { q ->
                q.prices.map { (sel, price) ->
                    OddsEntity(matchId, q.bookmaker, q.market, q.line, sel, price,
                        Instant.parse(q.capturedAt).epochSecond, q.isClosing, q.isSharp)
                }
            })
            null
        } else mapError(resp.code(), resp.errorBody()?.string())
    } catch (e: Exception) { AppError.Offline }

    suspend fun prune() =
        matchDao.pruneOlderThan(Instant.now().minusSeconds(90L * 86400).epochSecond)

    /** Kullanıcının kendi bahisçisinde gördüğü oranı girer — edge/Kelly bundan hesaplanır. */
    suspend fun setLocalOdds(matchId: Long, market: String, prices: Map<String, Double>) {
        val now = Instant.now().epochSecond
        oddsDao.upsert(prices.map { (sel, p) ->
            OddsEntity(matchId, "MANUEL", market, null, sel, p, now,
                isClosing = false, isSharp = false)
        })
    }

    /** Sunucudan gelen 402/429'u kullanıcıya anlamlı hataya çevirir. */
    private fun mapError(code: Int, body: String?): AppError {
        val detail = runCatching {
            Json { ignoreUnknownKeys = true }
                .parseToJsonElement(body ?: "{}")
        }.getOrNull()
        return when (code) {
            402 -> AppError.UpgradeRequired(
                feature = detail?.jsonFieldOrNull("feature") ?: "",
                requiredTier = detail?.jsonFieldOrNull("required_tier") ?: "PRO")
            429 -> AppError.QuotaExceeded(
                quota = detail?.jsonFieldOrNull("quota") ?: "match_analysis",
                limit = detail?.jsonFieldOrNull("limit")?.toIntOrNull() ?: 3,
                resetsAt = detail?.jsonFieldOrNull("resets_at") ?: "")
            else -> AppError.Server("Sunucu hatası ($code)")
        }
    }
}

private fun kotlinx.serialization.json.JsonElement.jsonFieldOrNull(key: String): String? =
    runCatching {
        val detail = (this as kotlinx.serialization.json.JsonObject)["detail"]
                as? kotlinx.serialization.json.JsonObject ?: return null
        (detail[key] as? kotlinx.serialization.json.JsonPrimitive)?.content
    }.getOrNull()

private fun MatchWithTeams.toDomain(): Match? {
    val lg = league ?: return null
    val h = home ?: return null
    val a = away ?: return null
    return Match(
        id = match.id,
        league = League(lg.id, lg.name, lg.country, lg.tier, lg.dataQuality),
        home = Team(h.id, h.name, h.shortName, h.crestUrl),
        away = Team(a.id, a.name, a.shortName, a.crestUrl),
        kickoff = Instant.ofEpochSecond(match.kickoffEpoch),
        status = runCatching { MatchStatus.valueOf(match.status) }.getOrDefault(MatchStatus.SCHEDULED),
        homeGoals = match.homeGoals, awayGoals = match.awayGoals,
        lambdaHome = match.lambdaHome, lambdaAway = match.lambdaAway, rho = match.rho,
        modelConfidence = match.modelConfidence,
        bestEdgePct = match.bestEdgePct, hasValue = match.hasValue,
        pHome = match.pHome, pDraw = match.pDraw, pAway = match.pAway,
        pOver25 = match.pOver25, pBtts = match.pBtts, minute = match.minute
    )
}

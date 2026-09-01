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
            .map { rows -> rows.map { it.toDomain() } }

    fun observeValueBoard(): Flow<List<Match>> =
        matchDao.observeValueBoard(Instant.now().epochSecond).map { it.map { r -> r.toDomain() } }

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
        // Render ucretsiz plan soguk baslangicta 30-60 sn uyanabilir; birkac kez dene.
        var resp = api.matches(from.toString(), to.toString())
        var tries = 0
        while (!resp.isSuccessful && resp.code() >= 500 && tries < 3) {
            tries++
            delay(5000L * tries)
            resp = api.matches(from.toString(), to.toString())
        }
        if (resp.isSuccessful) {
            val body = resp.body()!!
            val now = Instant.now().epochSecond
            matchDao.upsertLeagues(body.leagues.map {
                LeagueEntity(it.id, it.name, it.country, it.tier, it.dataQuality, it.strengthCoef)
            })
            matchDao.upsertTeams(body.teams.map {
                TeamEntity(it.id, it.name, it.shortName, it.crestUrl)
            })
            matchDao.upsert(body.matches.map { m ->
                MatchEntity(m.id, m.leagueId, m.homeTeamId, m.awayTeamId,
                    Instant.parse(m.kickoff).epochSecond, m.status, m.homeGoals, m.awayGoals,
                    m.lambdaHome, m.lambdaAway, m.rho, m.modelConfidence,
                    m.bestEdgePct, m.hasValue, now)
            })
            null
        } else mapError(resp.code(), resp.errorBody()?.string())
    } catch (e: Exception) {
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

private fun MatchWithTeams.toDomain() = Match(
    id = match.id,
    league = League(league.id, league.name, league.country, league.tier, league.dataQuality),
    home = Team(home.id, home.name, home.shortName, home.crestUrl),
    away = Team(away.id, away.name, away.shortName, away.crestUrl),
    kickoff = Instant.ofEpochSecond(match.kickoffEpoch),
    status = MatchStatus.valueOf(match.status),
    homeGoals = match.homeGoals, awayGoals = match.awayGoals,
    lambdaHome = match.lambdaHome, lambdaAway = match.lambdaAway, rho = match.rho,
    modelConfidence = match.modelConfidence,
    bestEdgePct = match.bestEdgePct, hasValue = match.hasValue
)

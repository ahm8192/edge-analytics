package com.ahmet.edge.data.remote

import com.ahmet.edge.billing.EntitlementDto
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.Response
import retrofit2.http.*

interface EdgeApi {

    @GET("v1/matches")
    suspend fun matches(
        @Query("from") fromIso: String,
        @Query("to") toIso: String,
        @Query("league_id") leagueId: Long? = null
    ): Response<MatchListDto>

    /** Kota bu uçta tüketilir; 429 dönerse ücretsiz hak bitmiştir. */
    @GET("v1/matches/{id}/analysis")
    suspend fun analysis(@Path("id") id: Long): Response<AnalysisDto>

    @GET("v1/matches/{id}/odds")
    suspend fun odds(@Path("id") id: Long,
                     @Query("market") market: String = "1X2"): Response<OddsListDto>

    /** PRO: açılıştan kapanışa oran serisi. */
    @GET("v1/matches/{id}/odds/movement")
    suspend fun oddsMovement(@Path("id") id: Long,
                             @Query("market") market: String,
                             @Query("selection") selection: String): Response<MovementDto>

    @GET("v1/model/parameters")
    suspend fun modelParameters(@Query("league_id") leagueId: Long): Response<ModelParamsDto>

    @POST("billing/verify")
    suspend fun verifyPurchase(@Body body: VerifyRequest): Response<EntitlementDto>

    @GET("billing/entitlement")
    suspend fun entitlement(): Response<EntitlementDto>
}

@Serializable data class VerifyRequest(@SerialName("purchase_token") val purchaseToken: String)

@Serializable
data class MatchListDto(val matches: List<MatchDto>, val leagues: List<LeagueDto>,
                        val teams: List<TeamDto>)

@Serializable
data class MatchDto(
    val id: Long,
    @SerialName("league_id") val leagueId: Long,
    @SerialName("home_team_id") val homeTeamId: Long,
    @SerialName("away_team_id") val awayTeamId: Long,
    val kickoff: String,
    val status: String,
    @SerialName("home_goals") val homeGoals: Int? = null,
    @SerialName("away_goals") val awayGoals: Int? = null,
    @SerialName("lambda_home") val lambdaHome: Double? = null,
    @SerialName("lambda_away") val lambdaAway: Double? = null,
    val rho: Double = -0.03,
    @SerialName("model_confidence") val modelConfidence: Double = 1.0,
    @SerialName("best_edge_pct") val bestEdgePct: Double? = null,
    @SerialName("has_value") val hasValue: Boolean = false,
    // Sunucudan gelen kalibre olasılıklar (varsa cihazda hesaplamaya tercih edilir)
    @SerialName("p_home") val pHome: Double? = null,
    @SerialName("p_draw") val pDraw: Double? = null,
    @SerialName("p_away") val pAway: Double? = null,
    @SerialName("p_over25") val pOver25: Double? = null,
    @SerialName("p_btts") val pBtts: Double? = null
)

@Serializable data class LeagueDto(val id: Long, val name: String, val country: String,
                                   val tier: Int,
                                   @SerialName("data_quality") val dataQuality: Double = 1.0,
                                   @SerialName("strength_coef") val strengthCoef: Double = 1.0)

@Serializable data class TeamDto(val id: Long, val name: String,
                                 @SerialName("short_name") val shortName: String,
                                 @SerialName("crest_url") val crestUrl: String? = null)

@Serializable
data class AnalysisDto(
    @SerialName("match_id") val matchId: Long,
    @SerialName("lambda_home") val lambdaHome: Double,
    @SerialName("lambda_away") val lambdaAway: Double,
    val rho: Double,
    @SerialName("model_confidence") val modelConfidence: Double,
    @SerialName("context_factors") val contextFactors: List<ContextFactorDto> = emptyList(),
    @SerialName("explanation") val explanation: Map<String, Double> = emptyMap(),
    @SerialName("quota_remaining") val quotaRemaining: Int = -1
)

@Serializable data class ContextFactorDto(val label: String, val value: String,
                                          val impact: Double, val note: String? = null)

@Serializable data class OddsListDto(val quotes: List<QuoteDto>)
@Serializable data class QuoteDto(val bookmaker: String, val market: String,
                                  val line: Double? = null,
                                  val prices: Map<String, Double>,
                                  @SerialName("captured_at") val capturedAt: String,
                                  @SerialName("is_closing") val isClosing: Boolean = false,
                                  @SerialName("is_sharp") val isSharp: Boolean = false)

@Serializable data class MovementDto(val points: List<PointDto>)
@Serializable data class PointDto(val at: String, val price: Double,
                                  val bookmaker: String)

/** Cihazda offline hesaplama için indirilen model parametreleri. */
@Serializable
data class ModelParamsDto(
    @SerialName("league_id") val leagueId: Long,
    val version: String,
    @SerialName("home_adv") val homeAdv: Double,
    val rho: Double,
    val attack: Map<String, Double>,
    val defence: Map<String, Double>,
    @SerialName("fitted_at") val fittedAt: String
)

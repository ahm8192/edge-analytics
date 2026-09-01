package com.ahmet.edge.ui.screen

import androidx.lifecycle.*
import com.ahmet.edge.billing.EntitlementState
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.core.AppError
import com.ahmet.edge.data.repo.*
import com.ahmet.edge.domain.engine.*
import com.ahmet.edge.domain.model.*
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.Instant
import javax.inject.Inject

data class MatchDetailUi(
    val match: Match? = null,
    val probs1x2: Map<String, Double> = emptyMap(),
    val marketProbs: Map<String, Double> = emptyMap(),
    val prices: Map<String, Double> = emptyMap(),
    val edges: List<EdgeResult> = emptyList(),
    val overUnder: Map<String, Double> = emptyMap(),
    val btts: Map<String, Double> = emptyMap(),
    val handicap: Map<String, Double> = emptyMap(),
    val topScores: List<Pair<String, Double>> = emptyList(),
    val context: List<ContextFactor> = emptyList(),
    val movement: List<OddsPoint> = emptyList(),
    val stake: StakeResult? = null,
    val bankroll: Bankroll? = null,
    val marginPct: Double = 0.0,
    val error: AppError? = null,
    val loading: Boolean = true
)

@OptIn(ExperimentalCoroutinesApi::class)
@HiltViewModel
class MatchDetailViewModel @Inject constructor(
    savedState: SavedStateHandle,
    private val matches: MatchRepository,
    private val betting: BettingRepository,
    entitlements: EntitlementRepository
) : ViewModel() {

    private val matchId: Long = savedState.get<String>("id")?.toLongOrNull() ?: 0L
    private val error = MutableStateFlow<AppError?>(null)
    private val loading = MutableStateFlow(true)

    /**
     * Tüm hesap cihazda yapılır. Sunucu sadece lambda/mu ve oran verir.
     * Bu sayede ağ kesilse bile ekran çalışır ve anında tepki verir.
     */
    val ui: StateFlow<MatchDetailUi> = combine(
        matches.observeMatch(matchId),
        matches.observeOdds(matchId, "1X2"),
        matches.observeContext(matchId),
        betting.observeBankroll(),
        entitlements.state
    ) { match, prices, context, bankroll, ent ->
        if (match?.lambdaHome == null || match.lambdaAway == null) {
            return@combine MatchDetailUi(match = match, context = context,
                bankroll = bankroll, error = error.value, loading = loading.value)
        }

        val m = PoissonMath.scoreMatrix(match.lambdaHome, match.lambdaAway, match.rho)
        // Sunucudan kalibre 1X2 geldiyse onu kullan, yoksa matristen
        val p1x2 = if (match.pHome != null && match.pDraw != null && match.pAway != null)
            mapOf("HOME" to match.pHome, "DRAW" to match.pDraw, "AWAY" to match.pAway)
        else Markets.oneXtwo(m)

        // Ücretsiz katman çarpımsal, abone Shin ile temizler (madde 78, 79)
        val useShin = ent.allows(Feature.CALIBRATED_PROB)
        val implied = if (prices.size >= 2) {
            val keys = prices.keys.toList()
            val vals = keys.map { prices.getValue(it) }
            keys.zip(if (useShin) Devig.shin(vals) else Devig.multiplicative(vals)).toMap()
        } else emptyMap()

        val edges = if (ent.allows(Feature.EDGE_DETECTION) && prices.isNotEmpty())
            Edge.compute(p1x2, prices, sampleConfidence = match.modelConfidence,
                         useShin = useShin)
        else emptyList()

        val best = edges.firstOrNull { it.isValue }
        val stake = if (ent.allows(Feature.KELLY_STAKE) && best != null)
            Kelly.stake(best.modelProb, best.takenPrice, bankroll.current,
                openExposure = bankroll.openExposure / bankroll.current.coerceAtLeast(1.0),
                modelConfidence = match.modelConfidence)
        else null

        MatchDetailUi(
            match = match,
            probs1x2 = p1x2,
            marketProbs = implied,
            prices = prices,
            edges = edges,
            overUnder = if (ent.allows(Feature.ALL_MARKETS)) {
                match.pOver25?.let { mapOf("OVER" to it, "UNDER" to 1.0 - it) }
                    ?: Markets.overUnder(m, 2.5)
            } else emptyMap(),
            btts = if (ent.allows(Feature.ALL_MARKETS)) {
                match.pBtts?.let { mapOf("YES" to it, "NO" to 1.0 - it) }
                    ?: Markets.btts(m)
            } else emptyMap(),
            handicap = if (ent.allows(Feature.ALL_MARKETS)) Markets.asianHandicap(m, -0.5) else emptyMap(),
            topScores = if (ent.allows(Feature.ALL_MARKETS)) Markets.topScores(m) else emptyList(),
            context = if (ent.allows(Feature.CONTEXT_ADJUST)) context else emptyList(),
            stake = stake,
            bankroll = bankroll,
            marginPct = if (prices.size >= 2) Devig.marginPct(prices.values.toList()) else 0.0,
            error = error.value,
            loading = loading.value
        )
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), MatchDetailUi())

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        loading.value = true
        error.value = matches.refreshAnalysis(matchId) ?: matches.refreshOdds(matchId)
        loading.value = false
    }

    fun dismissError() { error.value = null }

    /** Kullanıcı kendi bahisçisinin oranını girer -> edge/Kelly canlanır. */
    fun setManualOdds(home: Double, draw: Double, away: Double) = viewModelScope.launch {
        matches.setLocalOdds(matchId, "1X2",
            mapOf("HOME" to home, "DRAW" to draw, "AWAY" to away))
    }

    /** Seçilen tarafın oran hareketi — PRO. Ekran açıkken tembel yüklenir. */
    private val selectedForChart = MutableStateFlow("HOME")

    val movement: StateFlow<List<OddsPoint>> = selectedForChart
        .flatMapLatest { sel -> matches.observeMovement(matchId, "1X2", sel) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun selectForChart(selection: String) { selectedForChart.value = selection }

    /** Martingale uyarısı için geçmiş bağlamı. */
    val recentOutcomes: StateFlow<List<String>> = betting.observeRecentOutcomes()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val averageStake: StateFlow<Double> = betting.observeAverageStake()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0.0)

    /** Oynasın oynamasın kaydet — model denetimi kağıt üstü kayıtlar olmadan eksiktir. */
    fun recordBet(selection: String, price: Double, prob: Double,
                  stake: Double, actuallyPlaced: Boolean) = viewModelScope.launch {
        val s = ui.value
        val m = s.match ?: return@launch
        betting.record(
            Bet(matchId = m.id, matchLabel = "${m.home.shortName}–${m.away.shortName}",
                market = "1X2", selection = selection, modelProb = prob,
                takenPrice = price, stake = stake, placedAt = Instant.now(),
                wasPlaced = actuallyPlaced),
            bankrollBefore = s.bankroll?.current ?: 0.0
        )
    }
}

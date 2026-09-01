package com.ahmet.edge.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.LocalEntitlement
import com.ahmet.edge.data.repo.MatchRepository
import com.ahmet.edge.domain.engine.Markets
import com.ahmet.edge.domain.engine.PoissonMath
import com.ahmet.edge.domain.model.Match
import com.ahmet.edge.ui.component.*
import com.ahmet.edge.ui.theme.DataStyle
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.inject.Inject

@HiltViewModel
class MatchListViewModel @Inject constructor(
    private val repo: MatchRepository
) : ViewModel() {
    private val from = Instant.now()
    private val to = Instant.now().plusSeconds(7 * 86400)

    val matches: StateFlow<List<Match>> = repo.observeWindow(from, to)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val refreshing = MutableStateFlow(false)

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        if (!refreshing.compareAndSet(expect = false, update = true)) return@launch
        try {
            repo.refreshWindow(from, to)
            repo.prune()
        } finally {
            refreshing.value = false
        }
    }
}

private val TR = Locale("tr")
private val timeFmt = DateTimeFormatter.ofPattern("HH:mm", TR)
private val dayFmt = DateTimeFormatter.ofPattern("EEE d MMM", TR)

private fun oneXtwo(m: Match): Triple<Double, Double, Double> {
    val mat = PoissonMath.scoreMatrix(m.lambdaHome ?: 1.35, m.lambdaAway ?: 1.10, m.rho)
    val d = Markets.oneXtwo(mat)
    return Triple(d["HOME"] ?: 0.34, d["DRAW"] ?: 0.33, d["AWAY"] ?: 0.33)
}

@Composable
fun MatchListScreen(
    onOpen: (Long) -> Unit,
    onUpgrade: () -> Unit,
    vm: MatchListViewModel = hiltViewModel()
) {
    val matches by vm.matches.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val ent = LocalEntitlement.current
    val quota = ent.quotas["match_analysis"] ?: 0
    val showEdge = ent.allows(Feature.EDGE_DETECTION)

    val grouped = remember(matches) {
        matches.groupBy { it.kickoff.atZone(ZoneId.systemDefault()).toLocalDate() }
            .toSortedMap()
    }

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        ScreenHeader(
            title = "Önümüzdeki 7 gün",
            right = if (matches.isNotEmpty()) "${matches.size} MAÇ"
            else if (refreshing) "YÜKLENİYOR" else null
        )

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp)
        ) {
            if (!ent.isSubscriber) item { QuotaStrip(quota, onUpgrade) }

            if (ent.inGracePeriod) item {
                Text("BAĞLANTI YOK — KAYITLI ANALİZLER",
                    style = LabelMono, color = Ink.caution,
                    modifier = Modifier.padding(vertical = 2.dp))
            }

            if (matches.isEmpty()) {
                if (refreshing) items(5) { Spacer(Modifier.height(2.dp)); Skeleton(Modifier.height(116.dp)) }
                else item {
                    EmptyState(
                        "Bu aralıkta maç yok",
                        "Önümüzdeki 7 günde takip edilen liglerde fikstür bulunamadı.",
                        action = { GhostButton("Yenile", vm::refresh, Modifier.width(160.dp)) }
                    )
                }
            }

            grouped.forEach { (day, dayMatches) ->
                item(key = "h$day") {
                    SectionLabel(day.format(dayFmt), Modifier.padding(top = 6.dp))
                }
                items(dayMatches, key = { it.id }) { m ->
                    MatchCard(m, showEdge) { onOpen(m.id) }
                }
            }
        }
    }
}

@Composable
fun ScreenHeader(title: String, right: String? = null, sub: String? = null) {
    Column(Modifier.fillMaxWidth().padding(16.dp, 14.dp, 16.dp, 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = MaterialTheme.typography.headlineSmall, color = Ink.text,
                modifier = Modifier.weight(1f))
            if (right != null) Text(right, style = LabelMono, color = Ink.faint)
        }
        if (sub != null) {
            Spacer(Modifier.height(3.dp))
            Text(sub, style = MaterialTheme.typography.bodySmall, color = Ink.muted)
        }
    }
    Hairline()
}

@Composable
private fun QuotaStrip(remaining: Int, onUpgrade: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp))
            .background(Ink.accentDim)
            .border(1.dp, Ink.accent.copy(alpha = 0.25f), RoundedCornerShape(6.dp))
            .clickable(onClick = onUpgrade)
            .padding(horizontal = 12.dp, vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            if (remaining > 0) "BUGÜN $remaining ANALİZ HAKKI" else "GÜNLÜK ANALİZ HAKKI DOLDU",
            style = LabelMono, color = if (remaining > 0) Ink.accent else Ink.caution,
            modifier = Modifier.weight(1f)
        )
        Text("SINIRSIZA GEÇ →", style = LabelMono, color = Ink.accent)
    }
}

@Composable
fun MatchCard(m: Match, showEdge: Boolean, onClick: () -> Unit) {
    val (h, d, a) = remember(m.id, m.lambdaHome, m.lambdaAway) { oneXtwo(m) }
    val kickoff = remember(m.id) { m.kickoff.atZone(ZoneId.systemDefault()).format(timeFmt) }

    Panel(onClick = onClick, padding = PaddingValues(14.dp, 12.dp, 14.dp, 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(m.league.name.uppercase(TR), style = LabelMono.copy(fontSize = 10.sp),
                color = Ink.faint, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false))
            Text("  ·  $kickoff", style = DataStyle.copy(fontSize = 11.sp), color = Ink.muted)
            Spacer(Modifier.weight(1f))
            ConfidenceMeter(m.modelConfidence)
        }

        Spacer(Modifier.height(11.dp))

        TeamLine(m.home.crestUrl, m.home.shortName.ifBlank { m.home.name })
        Spacer(Modifier.height(7.dp))
        TeamLine(m.away.crestUrl, m.away.shortName.ifBlank { m.away.name })

        Spacer(Modifier.height(12.dp))
        ProbBar3(h, d, a)
        Spacer(Modifier.height(8.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            ProbLegendRow(h, d, a, Modifier.weight(1f))
            if (showEdge && m.hasValue && m.bestEdgePct != null) {
                Spacer(Modifier.width(10.dp))
                EdgeTag(m.bestEdgePct)
            }
        }
    }
}

@Composable
private fun TeamLine(crest: String?, name: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        TeamCrest(crest, name, 24.dp)
        Spacer(Modifier.width(10.dp))
        Text(name, style = MaterialTheme.typography.titleMedium, color = Ink.text,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

// ---------------------------------------------------------------- Değer tablosu
@Composable
fun ValueBoardScreen(
    onOpen: (Long) -> Unit,
    onUpgrade: () -> Unit,
    vm: ValueBoardViewModel = hiltViewModel()
) {
    val ent = LocalEntitlement.current
    val matches by vm.matches.collectAsState()

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        ScreenHeader(
            "Değer tablosu",
            right = if (ent.allows(Feature.EDGE_DETECTION) && matches.isNotEmpty())
                "${matches.size} FIRSAT" else null,
            sub = "Modelin piyasayı geçtiği maçlar, kenar payına göre sıralı."
        )

        if (!ent.allows(Feature.EDGE_DETECTION)) {
            LockedFeaturePane(
                "Değer tablosu PRO",
                "Model, piyasa oranının işaret ettiğinden daha olası gördüğü maçları " +
                    "burada toplar ve kenar payına göre sıralar. %2 altı gürültü sayılır, girmez.",
                onUpgrade
            )
            return
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 24.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp)
        ) {
            items(matches, key = { it.id }) { m -> MatchCard(m, true) { onOpen(m.id) } }
            if (matches.isEmpty()) item {
                EmptyState(
                    "Şu anda değerli maç yok",
                    "Bu iyi bir haber — model zorlama bahis üretmiyor. Fikstür ilerledikçe kontrol et."
                )
            }
        }
    }
}

@Composable
fun LockedFeaturePane(title: String, body: String, onUpgrade: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(28.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            Modifier.size(44.dp).clip(RoundedCornerShape(9.dp))
                .border(1.dp, Ink.accent.copy(alpha = 0.4f), RoundedCornerShape(9.dp)),
            contentAlignment = Alignment.Center
        ) { Text("λ", style = DataStyle.copy(fontSize = 22.sp), color = Ink.accent) }
        Spacer(Modifier.height(16.dp))
        Text(title, style = MaterialTheme.typography.headlineSmall, color = Ink.text)
        Spacer(Modifier.height(8.dp))
        Text(body, style = MaterialTheme.typography.bodyMedium, color = Ink.muted,
            modifier = Modifier.padding(horizontal = 4.dp))
        Spacer(Modifier.height(22.dp))
        PrimaryButton("Planları gör", onUpgrade)
    }
}

@HiltViewModel
class ValueBoardViewModel @Inject constructor(repo: MatchRepository) : ViewModel() {
    val matches = repo.observeValueBoard()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
}

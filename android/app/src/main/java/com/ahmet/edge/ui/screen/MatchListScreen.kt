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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
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
    private val repo: MatchRepository,
    private val betting: com.ahmet.edge.data.repo.BettingRepository,
    val coupon: com.ahmet.edge.domain.CouponStore,
) : ViewModel() {
    private val from = Instant.now()
    private val to = Instant.now().plusSeconds(7 * 86400)

    val matches: StateFlow<List<Match>> = repo.observeWindow(from, to)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val refreshing = MutableStateFlow(false)

    val bankroll = betting.observeBankroll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000),
            com.ahmet.edge.domain.model.Bankroll(0.0, 0.0, 0.0, 0.0))
    val openBets = betting.observeOpenCount()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    init {
        refresh()
        // Canlı maç varsa otomatik tazele
        viewModelScope.launch {
            while (true) {
                kotlinx.coroutines.delay(60_000)
                if (matches.value.any {
                        it.status == com.ahmet.edge.domain.model.MatchStatus.LIVE
                    }) refresh()
            }
        }
    }

    fun refresh() = viewModelScope.launch {
        if (!refreshing.compareAndSet(expect = false, update = true)) return@launch
        try {
            repo.refreshWindow(from, to)
            repo.prune()
            runCatching { betting.autoSettle() }   // biten bahisleri kapat
        } finally {
            refreshing.value = false
        }
    }
}

private val TR = Locale("tr")
private val timeFmt = DateTimeFormatter.ofPattern("HH:mm", TR)
private val dayFmt = DateTimeFormatter.ofPattern("EEE d MMM", TR)

private fun oneXtwo(m: Match): Triple<Double, Double, Double> {
    // Sunucudan kalibre olasılık geldiyse onu kullan
    if (m.pHome != null && m.pDraw != null && m.pAway != null) {
        return Triple(m.pHome, m.pDraw, m.pAway)
    }
    val mat = PoissonMath.scoreMatrix(m.lambdaHome ?: 1.35, m.lambdaAway ?: 1.10, m.rho)
    val d = Markets.oneXtwo(mat)
    return Triple(d["HOME"] ?: 0.34, d["DRAW"] ?: 0.33, d["AWAY"] ?: 0.33)
}

@Composable
fun MatchListScreen(
    onOpen: (Long) -> Unit,
    onUpgrade: () -> Unit,
    onCoupon: () -> Unit = {},
    vm: MatchListViewModel = hiltViewModel()
) {
    val matches by vm.matches.collectAsState()
    val refreshing by vm.refreshing.collectAsState()
    val bankroll by vm.bankroll.collectAsState()
    val openBets by vm.openBets.collectAsState()
    val couponPicks by vm.coupon.picks.collectAsState()
    val ent = LocalEntitlement.current
    val quota = ent.quotas["match_analysis"] ?: 0
    val showEdge = ent.allows(Feature.EDGE_DETECTION)

    var league by rememberSaveable { mutableStateOf<String?>(null) }
    val leagues = remember(matches) {
        matches.map { it.league.name }.distinct().sorted()
    }
    val filtered = remember(matches, league) {
        if (league == null) matches else matches.filter { it.league.name == league }
    }
    val grouped = remember(filtered) {
        filtered.groupBy { it.kickoff.atZone(ZoneId.systemDefault()).toLocalDate() }
            .toSortedMap()
    }

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        ScreenHeader(
            title = "Önümüzdeki 7 gün",
            right = if (matches.isNotEmpty()) "${filtered.size} MAÇ"
            else if (refreshing) "YÜKLENİYOR" else null
        )
        if (leagues.size > 1) {
            LeagueTabs(leagues, league) { league = it }
            Hairline()
        }
        if (couponPicks.isNotEmpty()) {
            val a = remember(couponPicks) { vm.coupon.analyze(couponPicks) }
            Row(
                Modifier.fillMaxWidth().background(Ink.accentDim)
                    .clickable(onClick = onCoupon)
                    .padding(horizontal = 16.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("KUPON · ${couponPicks.size} SEÇİM", style = LabelMono, color = Ink.accent,
                    modifier = Modifier.weight(1f))
                Text("ORAN ${fmt(a.combinedOdds)}  ·  ${signedPct(a.edgePct)}  →",
                    style = LabelMono,
                    color = if (a.edgePct > 0 && !a.sameMatch) Ink.signal else Ink.muted)
            }
            Hairline()
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 4.dp, 16.dp, 24.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp)
        ) {
            item {
                val valCount = filtered.count { it.hasValue }
                Panel(padding = PaddingValues(14.dp, 12.dp, 14.dp, 12.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        StatCell("MAÇ", filtered.size.toString(), Ink.text)
                        StatCell("DEĞER", valCount.toString(),
                            if (valCount > 0) Ink.signal else Ink.muted)
                        StatCell("AÇIK BAHİS", openBets.toString(), Ink.text)
                        StatCell(
                            "KASA",
                            if (bankroll.starting > 0) signedPct(bankroll.roi) else "—",
                            if (bankroll.starting <= 0) Ink.muted
                            else if (bankroll.roi >= 0) Ink.signal else Ink.caution
                        )
                    }
                }
            }

            if (!ent.isSubscriber) item { QuotaStrip(quota, onUpgrade) }

            if (ent.inGracePeriod) item {
                Text("BAĞLANTI YOK — KAYITLI ANALİZLER",
                    style = LabelMono, color = Ink.caution,
                    modifier = Modifier.padding(vertical = 2.dp))
            }

            if (filtered.isEmpty()) {
                if (refreshing) items(5) { Spacer(Modifier.height(2.dp)); Skeleton(Modifier.height(116.dp)) }
                else item {
                    EmptyState(
                        if (league != null) "$league — maç yok" else "Bu aralıkta maç yok",
                        "Önümüzdeki 7 günde takip edilen liglerde fikstür bulunamadı.",
                        action = { GhostButton("Yenile", vm::refresh, Modifier.width(160.dp)) }
                    )
                }
            }

            val live = filtered.filter { it.status == com.ahmet.edge.domain.model.MatchStatus.LIVE }
            if (live.isNotEmpty()) {
                item(key = "h-live") {
                    SectionLabel("● CANLI", Modifier.padding(top = 6.dp))
                }
                items(live, key = { it.id }) { m -> MatchCard(m, showEdge) { onOpen(m.id) } }
            }

            grouped.forEach { (day, dayMatches) ->
                val notLive = dayMatches.filter {
                    it.status != com.ahmet.edge.domain.model.MatchStatus.LIVE
                }
                if (notLive.isEmpty()) return@forEach
                item(key = "h$day") {
                    SectionLabel(day.format(dayFmt), Modifier.padding(top = 6.dp))
                }
                items(notLive, key = { it.id }) { m ->
                    MatchCard(m, showEdge) { onOpen(m.id) }
                }
            }
        }
    }
}

@Composable
fun LeagueTabs(leagues: List<String>, selected: String?, onSelect: (String?) -> Unit) {
    androidx.compose.foundation.lazy.LazyRow(
        Modifier.fillMaxWidth().background(Ink.base),
        contentPadding = PaddingValues(16.dp, 10.dp, 16.dp, 10.dp),
        horizontalArrangement = Arrangement.spacedBy(7.dp)
    ) {
        item { LeagueChip("TÜMÜ", selected == null) { onSelect(null) } }
        items(leagues) { lg ->
            LeagueChip(lg.uppercase(TR), selected == lg) { onSelect(lg) }
        }
    }
}

@Composable
private fun LeagueChip(text: String, active: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.clip(RoundedCornerShape(5.dp))
            .background(if (active) Ink.accent else Ink.raised)
            .then(if (active) Modifier else Modifier.border(1.dp, Ink.line, RoundedCornerShape(5.dp)))
            .clickable(onClick = onClick)
            .padding(horizontal = 11.dp, vertical = 7.dp)
    ) {
        Text(text, style = LabelMono.copy(fontSize = 10.sp),
            color = if (active) Ink.base else Ink.muted)
    }
}

@Composable
fun ScreenHeader(title: String, right: String? = null, sub: String? = null) {
    Column(
        Modifier.fillMaxWidth()
            .statusBarsPadding()
            .padding(16.dp, 18.dp, 16.dp, 14.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(26.dp).clip(RoundedCornerShape(6.dp))
                    .background(Ink.accent.copy(alpha = 0.14f))
                    .border(1.dp, Ink.accent.copy(alpha = 0.35f), RoundedCornerShape(6.dp)),
                contentAlignment = Alignment.Center
            ) { Text("λ", style = DataStyle.copy(fontSize = 15.sp), color = Ink.accent) }
            Spacer(Modifier.width(10.dp))
            Text(title, style = MaterialTheme.typography.headlineSmall, color = Ink.text,
                modifier = Modifier.weight(1f))
            if (right != null) Text(right, style = LabelMono, color = Ink.faint)
        }
        if (sub != null) {
            Spacer(Modifier.height(6.dp))
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
    val pick = when (maxOf(h, d, a)) { h -> 0; d -> 1; else -> 2 }
    val homeName = m.home.shortName.ifBlank { m.home.name }
    val awayName = m.away.shortName.ifBlank { m.away.name }

    val isLive = m.status == com.ahmet.edge.domain.model.MatchStatus.LIVE

    Panel(onClick = onClick, padding = PaddingValues(16.dp, 13.dp, 16.dp, 14.dp)) {
        // üst: lig · saat/canlı  ————  güven  ⟩
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(m.league.name.uppercase(TR), style = LabelMono.copy(fontSize = 10.sp),
                color = Ink.faint, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false))
            if (isLive) {
                Spacer(Modifier.width(8.dp))
                Box(Modifier.size(6.dp).background(Ink.caution,
                    androidx.compose.foundation.shape.CircleShape))
                Spacer(Modifier.width(5.dp))
                Text("CANLI ${m.minute ?: 0}'", style = LabelMono.copy(fontSize = 10.sp),
                    color = Ink.caution)
            } else {
                Text("  ·  $kickoff", style = DataStyle.copy(fontSize = 11.sp),
                    color = Ink.muted, maxLines = 1)
            }
            Spacer(Modifier.weight(1f))
            ConfidenceMeter(m.modelConfidence)
            Spacer(Modifier.width(9.dp))
            Text("⟩", color = Ink.faint, style = MaterialTheme.typography.titleMedium)
        }

        Spacer(Modifier.height(13.dp))

        // eşleşme (canlıda skor, öncesinde adil oran)
        MatchupSide(m.home.crestUrl, homeName,
            if (isLive) null else 1.0 / h.coerceAtLeast(0.01), pick == 0,
            score = if (isLive) m.homeGoals else null)
        Spacer(Modifier.height(9.dp))
        MatchupSide(m.away.crestUrl, awayName,
            if (isLive) null else 1.0 / a.coerceAtLeast(0.01), pick == 2,
            score = if (isLive) m.awayGoals else null)

        Spacer(Modifier.height(14.dp))
        Hairline()
        Spacer(Modifier.height(12.dp))

        // 1 / X / 2 kolonları — modelin seçimi vurgulu
        Row(Modifier.fillMaxWidth()) {
            ProbColumn("1", h, pick == 0, Modifier.weight(1f))
            ProbColumn("X", d, pick == 1, Modifier.weight(1f))
            ProbColumn("2", a, pick == 2, Modifier.weight(1f))
        }
        Spacer(Modifier.height(10.dp))
        ProbBar3(h, d, a, height = 5.dp)

        if (showEdge && m.hasValue && m.bestEdgePct != null) {
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("DEĞER", style = LabelMono, color = Ink.signal)
                Spacer(Modifier.weight(1f))
                EdgeTag(m.bestEdgePct)
            }
        }
    }
}

@Composable
private fun MatchupSide(
    crest: String?, name: String, fairOdds: Double?, isPick: Boolean, score: Int? = null,
) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        TeamCrest(crest, name, 30.dp)
        Spacer(Modifier.width(12.dp))
        Text(
            name,
            style = MaterialTheme.typography.titleMedium,
            color = if (isPick) Ink.text else Ink.muted,
            fontWeight = if (isPick) FontWeight.SemiBold else FontWeight.Medium,
            maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f)
        )
        when {
            score != null -> Text("$score",
                style = DataStyle.copy(fontSize = 18.sp, fontWeight = FontWeight.SemiBold),
                color = Ink.text)
            fairOdds != null -> Text(fmt(fairOdds), style = DataStyle.copy(fontSize = 14.sp),
                color = if (isPick) Ink.text else Ink.faint)
        }
    }
}

@Composable
private fun ProbColumn(k: String, v: Double, isPick: Boolean, modifier: Modifier = Modifier) {
    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(k, style = LabelMono, color = if (isPick) Ink.accent else Ink.faint)
        Spacer(Modifier.height(4.dp))
        Text(
            pct0(v),
            style = DataStyle.copy(fontSize = 18.sp, fontWeight = FontWeight.SemiBold),
            color = if (isPick) Ink.text else Ink.muted
        )
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
            "Model leanları",
            right = if (ent.allows(Feature.EDGE_DETECTION) && matches.isNotEmpty())
                "${matches.size} MAÇ" else null,
            sub = "Modelin en güçlü kanaatleri — en net sonuç × güven. Maça girip " +
                "oranını yazarak kenar payını gör."
        )

        if (!ent.allows(Feature.EDGE_DETECTION)) {
            LockedFeaturePane(
                "Model leanları · PRO",
                "Modelin en net gördüğü maçları tek listede sıralar. Bir maça girip " +
                    "kendi bahisçinin oranını yazınca kenar payını ve önerilen tutarı hesaplar.",
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
                    "Yaklaşan maç yok",
                    "Fikstür geldikçe modelin kanaatleri burada sıralanır."
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
    // Modelin en güçlü kanaatleri: en olası sonucun olasılığına göre sıralı.
    val matches = repo.observeUpcoming(10)
        .map { list ->
            list.sortedByDescending { m ->
                val (h, d, a) = oneXtwo(m)
                maxOf(h, d, a) * m.modelConfidence
            }.take(40)
        }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
}

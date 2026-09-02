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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.shape.CircleShape
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
import com.ahmet.edge.ui.theme.PlexMono
import com.ahmet.edge.ui.theme.TeamStyle
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
        val valCount = filtered.count { it.hasValue }
        TerminalHeader(
            matchCount = filtered.size,
            valueCount = valCount,
            roi = if (bankroll.starting > 0) signedPct(bankroll.roi) else null,
            roiUp = bankroll.roi >= 0,
            openBets = openBets,
            loading = refreshing
        )
        if (leagues.size > 1) LeagueTabs(leagues, league) { league = it }
        Hairline()
        if (couponPicks.isNotEmpty()) {
            val a = remember(couponPicks) { vm.coupon.analyze(couponPicks) }
            Row(
                Modifier.fillMaxWidth().background(Ink.accentDim)
                    .clickable(onClick = onCoupon)
                    .padding(horizontal = 20.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("KUPON · ${couponPicks.size} SEÇİM", style = LabelMono, color = Ink.accent,
                    modifier = Modifier.weight(1f))
                Text("${fmt(a.combinedOdds)}   ${signedPct(a.edgePct)}  →",
                    style = LabelMono,
                    color = if (a.edgePct > 0 && !a.sameMatch) Ink.signal else Ink.muted)
            }
            Hairline()
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 28.dp)
        ) {
            if (!ent.isSubscriber) item {
                Box(Modifier.padding(16.dp, 12.dp, 16.dp, 2.dp)) { QuotaStrip(quota, onUpgrade) }
            }
            if (ent.inGracePeriod) item {
                Text("BAĞLANTI YOK — KAYITLI ANALİZLER",
                    style = LabelMono, color = Ink.caution,
                    modifier = Modifier.padding(20.dp, 10.dp))
            }

            if (filtered.isEmpty()) {
                if (refreshing) items(6) {
                    Box(Modifier.padding(16.dp, 8.dp)) {
                        Skeleton(Modifier.fillMaxWidth().height(70.dp))
                    }
                }
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
                item(key = "h-live") { DayDivider("● CANLI", live.size, accent = true) }
                items(live, key = { it.id }) { m ->
                    MatchCard(m, showEdge) { onOpen(m.id) }; Hairline()
                }
            } else if (filtered.isNotEmpty()) {
                item(key = "h-live-empty") {
                    val next = remember(filtered) {
                        filtered.filter { it.status == com.ahmet.edge.domain.model.MatchStatus.SCHEDULED }
                            .minByOrNull { it.kickoff }
                            ?.kickoff?.atZone(ZoneId.systemDefault())?.format(timeFmt)
                    }
                    DayDivider("● CANLI", 0, accent = true)
                    Text(
                        if (next != null) "Şu an takip edilen liglerde canlı maç yok · sıradaki $next"
                        else "Şu an takip edilen liglerde canlı maç yok",
                        style = LabelMono.copy(fontSize = 10.sp), color = Ink.faint,
                        modifier = Modifier.padding(start = 20.dp, end = 20.dp, top = 2.dp, bottom = 4.dp)
                    )
                }
            }

            grouped.forEach { (day, dayMatches) ->
                val notLive = dayMatches.filter {
                    it.status != com.ahmet.edge.domain.model.MatchStatus.LIVE
                }
                if (notLive.isEmpty()) return@forEach
                item(key = "h$day") {
                    DayDivider(day.format(dayFmt).uppercase(ROOT), notLive.size)
                }
                items(notLive, key = { it.id }) { m ->
                    MatchCard(m, showEdge) { onOpen(m.id) }; Hairline()
                }
            }
        }
    }
}

@Composable
private fun TerminalHeader(
    matchCount: Int, valueCount: Int, roi: String?, roiUp: Boolean,
    openBets: Int, loading: Boolean
) {
    Column(
        Modifier.fillMaxWidth().statusBarsPadding()
            .padding(start = 20.dp, end = 20.dp, top = 14.dp, bottom = 12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(24.dp).clip(RoundedCornerShape(7.dp))
                    .background(Ink.accent)
                    .border(1.dp, Color.White.copy(alpha = 0.18f), RoundedCornerShape(7.dp)),
                contentAlignment = Alignment.Center
            ) {
                Text("λ", style = TextStyle(fontFamily = PlexMono, fontWeight = FontWeight.Bold,
                    fontSize = 15.sp), color = Color(0xFF1A1400))
            }
            Spacer(Modifier.width(11.dp))
            Text("LAMBDA", style = TextStyle(fontFamily = PlexMono,
                fontWeight = FontWeight.Bold, fontSize = 22.sp, letterSpacing = 2.sp),
                color = Ink.text)
            Spacer(Modifier.weight(1f))
            Text(if (loading) "SENK…" else "7 GÜN", style = LabelMono, color = Ink.faint)
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(6.dp).clip(CircleShape)
                .background(if (valueCount > 0) Ink.accent else Ink.faint))
            Spacer(Modifier.width(9.dp))
            HeaderStat("$matchCount", "MAÇ")
            HeaderSep()
            HeaderStat("$valueCount", "DEĞER", if (valueCount > 0) Ink.signal else Ink.muted)
            HeaderSep()
            HeaderStat("$openBets", "AÇIK", if (openBets > 0) Ink.text else Ink.muted)
            HeaderSep()
            HeaderStat(roi ?: "—", "KASA",
                if (roi == null) Ink.muted else if (roiUp) Ink.signal else Ink.caution)
        }
    }
}

@Composable
private fun HeaderStat(value: String, label: String, tint: Color = Ink.text) {
    Row(verticalAlignment = Alignment.Bottom) {
        Text(value, style = DataStyle.copy(fontSize = 13.sp, fontWeight = FontWeight.SemiBold),
            color = tint)
        Spacer(Modifier.width(4.dp))
        Text(label, style = LabelMono, color = Ink.faint)
    }
}

@Composable
private fun HeaderSep() =
    Text("·", style = LabelMono, color = Ink.faint,
        modifier = Modifier.padding(horizontal = 9.dp))

@Composable
private fun DayDivider(label: String, count: Int, accent: Boolean = false) {
    Row(
        Modifier.fillMaxWidth().background(Ink.base)
            .padding(start = 20.dp, end = 20.dp, top = 17.dp, bottom = 7.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label, style = LabelMono.copy(fontSize = 12.sp),
            color = if (accent) Ink.live else Ink.muted, fontWeight = FontWeight.Medium)
        Spacer(Modifier.width(12.dp))
        Box(Modifier.weight(1f).height(2.dp).clip(RoundedCornerShape(1.dp)).background(Ink.line))
        Spacer(Modifier.width(12.dp))
        Text("$count", style = LabelMono, color = Ink.faint)
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
            LeagueChip(lg.uppercase(Locale.ROOT), selected == lg) { onSelect(lg) }
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

private val ROOT: Locale = Locale.ROOT

@Composable
fun ScreenHeader(title: String, right: String? = null, sub: String? = null) {
    Column(
        Modifier.fillMaxWidth()
            .statusBarsPadding()
            .padding(16.dp, 12.dp, 16.dp, 10.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(20.dp).clip(RoundedCornerShape(5.dp))
                    .background(Ink.accent.copy(alpha = 0.14f))
                    .border(1.dp, Ink.accent.copy(alpha = 0.35f), RoundedCornerShape(5.dp)),
                contentAlignment = Alignment.Center
            ) { Text("λ", style = DataStyle.copy(fontSize = 12.sp), color = Ink.accent) }
            Spacer(Modifier.width(9.dp))
            Text(title, style = MaterialTheme.typography.headlineSmall, color = Ink.text,
                modifier = Modifier.weight(1f))
            if (right != null) Text(right, style = LabelMono, color = Ink.faint)
        }
        if (sub != null) {
            Spacer(Modifier.height(5.dp))
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
    val (h, d, a) = remember(m.id, m.pHome, m.pDraw, m.pAway, m.lambdaHome) { oneXtwo(m) }
    val pickIdx = when (maxOf(h, d, a)) { h -> 0; d -> 1; else -> 2 }
    val pickProb = maxOf(h, d, a)
    val pickLabel = when (pickIdx) { 0 -> "1"; 1 -> "X"; else -> "2" }
    val isLive = m.status == com.ahmet.edge.domain.model.MatchStatus.LIVE
    val hasModel = m.pHome != null
    val hasVal = showEdge && m.hasValue && m.bestEdgePct != null
    val kickoff = remember(m.id) { m.kickoff.atZone(ZoneId.systemDefault()).format(timeFmt) }
    val homeName = m.home.shortName.ifBlank { m.home.name }
    val awayName = m.away.shortName.ifBlank { m.away.name }
    val (hc, ac) = remember(m.id) { TeamStyle.codes(m.home.name, m.away.name) }
    val homeColor = remember(m.id) { TeamStyle.color(m.home.name) }
    val awayColor = remember(m.id) { TeamStyle.color(m.away.name) }
    val spineColor = when {
        isLive -> Ink.live
        pickIdx == 2 -> awayColor
        else -> homeColor
    }

    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick)
            .height(IntrinsicSize.Min)
            .background(if (hasVal) Ink.accent.copy(alpha = 0.035f) else Color.Transparent)
    ) {
        Box(Modifier.width(4.dp).fillMaxHeight().background(spineColor))
        Column(
            Modifier.weight(1f).padding(start = 16.dp, top = 13.dp, bottom = 13.dp, end = 10.dp)
        ) {
            Text(m.league.name.uppercase(ROOT), style = LabelMono.copy(fontSize = 9.sp),
                color = Ink.faint, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(8.dp))
            TeamLine(hc, homeColor, homeName, hasModel && pickIdx == 0, if (isLive) m.homeGoals else null)
            Spacer(Modifier.height(5.dp))
            TeamLine(ac, awayColor, awayName, hasModel && pickIdx == 2, if (isLive) m.awayGoals else null)
            if (hasModel) {
                Spacer(Modifier.height(10.dp))
                SegBar(h, d, a, homeColor)
            } else if (isLive) {
                Spacer(Modifier.height(9.dp))
                Text("CANLI SKOR · model bu lig için kalibre değil",
                    style = LabelMono.copy(fontSize = 8.5.sp), color = Ink.faint, maxLines = 1)
            }
        }
        Column(
            Modifier.fillMaxHeight().width(84.dp)
                .padding(end = 16.dp, top = 13.dp, bottom = 13.dp),
            horizontalAlignment = Alignment.End,
            verticalArrangement = Arrangement.Center
        ) {
            Text(if (isLive) "${m.minute ?: 0}'" else kickoff,
                style = LabelMono, color = if (isLive) Ink.live else Ink.faint,
                maxLines = 1, softWrap = false)
            Spacer(Modifier.height(6.dp))
            if (isLive) {
                Text("${m.homeGoals ?: 0}–${m.awayGoals ?: 0}",
                    style = MaterialTheme.typography.displaySmall.copy(fontSize = 22.sp),
                    color = Ink.text, maxLines = 1, softWrap = false)
            } else {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(pickLabel, style = LabelMono.copy(fontSize = 11.sp), color = Ink.accent,
                        maxLines = 1, softWrap = false)
                    Spacer(Modifier.width(4.dp))
                    Text(pct0(pickProb),
                        style = MaterialTheme.typography.displaySmall.copy(fontSize = 21.sp),
                        color = Ink.text, maxLines = 1, softWrap = false)
                }
            }
            if (hasVal) {
                Spacer(Modifier.height(5.dp))
                Box(
                    Modifier.clip(RoundedCornerShape(4.dp)).background(Ink.signal)
                        .padding(horizontal = 6.dp, vertical = 2.dp)
                ) {
                    Text(
                        "+EV " + String.format(Locale.US, "%.1f", m.bestEdgePct!! * 100),
                        style = LabelMono.copy(fontSize = 10.sp, letterSpacing = 0.4.sp),
                        color = Color(0xFF04231A), maxLines = 1, softWrap = false
                    )
                }
            }
        }
    }
}

@Composable
private fun TeamLine(code: String, color: Color, name: String, isPick: Boolean, score: Int?) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Crest(code, color, 26.dp)
        Spacer(Modifier.width(11.dp))
        Text(name.uppercase(ROOT), style = MaterialTheme.typography.titleMedium,
            color = if (isPick) Ink.text else Ink.muted,
            fontWeight = if (isPick) FontWeight.SemiBold else FontWeight.Normal,
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        if (score != null) Text("$score",
            style = MaterialTheme.typography.displaySmall.copy(fontSize = 18.sp), color = Ink.text)
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

        Hairline()
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 24.dp)
        ) {
            items(matches, key = { it.id }) { m ->
                MatchCard(m, true) { onOpen(m.id) }; Hairline()
            }
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

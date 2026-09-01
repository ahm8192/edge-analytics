package com.ahmet.edge.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.LocalEntitlement
import com.ahmet.edge.core.AppError
import com.ahmet.edge.domain.engine.Confidence
import com.ahmet.edge.domain.engine.EdgeResult
import com.ahmet.edge.ui.component.*
import com.ahmet.edge.ui.theme.Ink
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MatchDetailScreen(
    onBack: () -> Unit,
    onUpgrade: () -> Unit,
    vm: MatchDetailViewModel = hiltViewModel()
) {
    val ui by vm.ui.collectAsState()
    val movement by vm.movement.collectAsState()
    val recentOutcomes by vm.recentOutcomes.collectAsState()
    val averageStake by vm.averageStake.collectAsState()
    val ent = LocalEntitlement.current
    val m = ui.match

    var recording by remember { mutableStateOf<EdgeResult?>(null) }

    recording?.let { e ->
        RecordBetSheet(
            matchLabel = m?.let { "${it.home.shortName}–${it.away.shortName}" } ?: "",
            selection = labelOf(e.selection),
            modelProb = e.modelProb,
            suggestedPrice = e.takenPrice,
            suggestedStake = ui.stake,
            bankroll = ui.bankroll?.current ?: 0.0,
            recentOutcomes = recentOutcomes,
            averageStake = averageStake,
            onDismiss = { recording = null },
            onConfirm = { price, stake, placed ->
                vm.recordBet(e.selection, price, e.modelProb, stake, placed)
                recording = null
            }
        )
    }

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        DetailHeader(
            onBack = onBack,
            home = m?.home?.let { it.shortName.ifBlank { it.name } } ?: "",
            away = m?.away?.let { it.shortName.ifBlank { it.name } } ?: "",
            homeCrest = m?.home?.crestUrl,
            awayCrest = m?.away?.crestUrl,
            meta = m?.let {
                "${it.league.name.uppercase(java.util.Locale("tr"))} · " +
                    dateFmt.format(it.kickoff.atZone(ZoneId.systemDefault()))
            } ?: ""
        )

        (ui.error as? AppError.QuotaExceeded)?.let { QuotaWall(it, onUpgrade, Modifier) }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 16.dp, 16.dp, 40.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {
            // ---- Ücretsiz: maç sonucu olasılığı -------------------------
            item {
                Section("Maç sonucu") {
                    listOf("HOME" to "1", "DRAW" to "X", "AWAY" to "2").forEach { (key, label) ->
                        val p = ui.probs1x2[key] ?: 0.0
                        val edge = ui.edges.firstOrNull { it.selection == key }
                        ProbabilityRow(
                            label = label,
                            modelProb = p,
                            marketProb = ui.marketProbs[key],
                            price = ui.prices[key],
                            fairPrice = if (p > 0) 1.0 / p else 0.0,
                            highlighted = edge?.isValue == true
                        )
                    }
                    if (ui.marginPct > 0) {
                        Spacer(Modifier.height(6.dp))
                        Text("Bahisçi marjı ${pct(ui.marginPct)} — adil oran bu çıkarıldıktan sonra hesaplandı.",
                            style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                    }
                }
            }

            // ---- PRO: değer tespiti -------------------------------------
            item {
                if (ent.allows(Feature.EDGE_DETECTION)) {
                    Section("Değer") {
                        val value = ui.edges.filter { it.isValue }
                        if (value.isEmpty()) {
                            Text("Bu maçta model piyasayı yenmiyor. Oynamamak da bir karardır.",
                                style = MaterialTheme.typography.bodyMedium, color = Ink.muted)
                        } else value.forEach { e ->
                            Row(Modifier.fillMaxWidth().padding(vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween) {
                                StatChip(labelOf(e.selection), signedPct(e.edgePct), Ink.signal)
                                StatChip("oran", fmt(e.takenPrice))
                                StatChip("güven", when (e.confidence) {
                                    Confidence.HIGH -> "yüksek"
                                    Confidence.MEDIUM -> "orta"
                                    Confidence.LOW -> "düşük"
                                })
                                TextButton(onClick = { recording = e }) {
                                    Text("Kaydet", color = Ink.signal,
                                        style = MaterialTheme.typography.labelMedium)
                                }
                            }
                        }
                    }
                } else LockedCard(Feature.EDGE_DETECTION, onUpgrade)
            }

            // ---- PRO: Kelly tutarı --------------------------------------
            item {
                if (ent.allows(Feature.KELLY_STAKE)) {
                    ui.stake?.let { s ->
                        Section("Önerilen tutar") {
                            if (s.skipped) {
                                Text(s.note ?: "Bu maçta oynanacak tutar yok.",
                                    color = Ink.muted,
                                    style = MaterialTheme.typography.bodyMedium)
                            } else {
                                Row(verticalAlignment = Alignment.Bottom,
                                    horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                    Text(fmt(s.stake), color = Ink.text,
                                        style = MaterialTheme.typography.displaySmall)
                                    Text("kasanın ${pct(s.pctBankroll)}'i",
                                        color = Ink.muted,
                                        style = MaterialTheme.typography.bodySmall)
                                }
                                s.cappedBy?.let {
                                    Text("Tutar $it nedeniyle sınırlandı.",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = Ink.caution)
                                }
                                Text("Çeyrek Kelly kullanıldı. Tam Kelly matematiksel " +
                                     "olarak optimaldir ama model hatasında kasayı yakar.",
                                    style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                            }
                        }
                    }
                } else LockedCard(Feature.KELLY_STAKE, onUpgrade)
            }

            // ---- PRO: oran hareketi -------------------------------------
            item {
                if (ent.allows(Feature.ODDS_MOVEMENT)) {
                    Section("Oran hareketi") {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf("HOME" to "1", "DRAW" to "X", "AWAY" to "2")
                                .forEach { (key, label) ->
                                    TextButton(onClick = { vm.selectForChart(key) }) {
                                        Text(label, color = Ink.muted)
                                    }
                                }
                        }
                        OddsMovementChart(
                            points = movement,
                            fairPrice = ui.probs1x2["HOME"]?.let { 1.0 / it }
                        )
                    }
                } else LockedCard(Feature.ODDS_MOVEMENT, onUpgrade)
            }

            // ---- PRO: diğer marketler -----------------------------------
            item {
                if (ent.allows(Feature.ALL_MARKETS)) {
                    Section("Diğer marketler") {
                        MarketLine("2.5 üst", ui.overUnder["OVER"])
                        MarketLine("2.5 alt", ui.overUnder["UNDER"])
                        MarketLine("KG var", ui.btts["YES"])
                        MarketLine("Ev -0.5 handikap", ui.handicap["HOME"])
                        if (ui.topScores.isNotEmpty()) {
                            Spacer(Modifier.height(10.dp))
                            Text("En olası skorlar",
                                style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                            ui.topScores.forEach { (score, p) -> MarketLine(score, p) }
                        }
                    }
                } else LockedCard(Feature.ALL_MARKETS, onUpgrade)
            }

            // ---- PRO: bağlam etkenleri ----------------------------------
            item {
                if (ent.allows(Feature.CONTEXT_ADJUST)) {
                    if (ui.context.isNotEmpty()) Section("Bağlam") {
                        ui.context.forEach { f ->
                            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp),
                                verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(f.label, color = Ink.text,
                                        style = MaterialTheme.typography.bodyMedium)
                                    f.note?.let {
                                        Text(it, color = Ink.faint,
                                            style = MaterialTheme.typography.bodySmall)
                                    }
                                }
                                Text(f.value, color = Ink.muted,
                                    style = MaterialTheme.typography.bodyMedium)
                                Spacer(Modifier.width(12.dp))
                                Text(signedPct(f.impact),
                                    color = if (f.impact > 0) Ink.signal else Ink.caution,
                                    style = MaterialTheme.typography.labelMedium)
                            }
                        }
                    }
                } else LockedCard(Feature.CONTEXT_ADJUST, onUpgrade)
            }

            // ---- ELITE: model açıklaması --------------------------------
            item {
                if (!ent.allows(Feature.MODEL_EXPLAIN))
                    LockedCard(Feature.MODEL_EXPLAIN, onUpgrade)
            }

            item {
                Text("Bu bir tahmin değil, olasılık dağılımıdır. Model doğru çalışsa " +
                     "bile tek maçta yanılabilir; anlamlı sonuç yüzlerce bahis sonrasında " +
                     "ortaya çıkar.",
                    style = MaterialTheme.typography.bodySmall, color = Ink.faint)
            }
        }
    }
}

@Composable
private fun DetailHeader(
    onBack: () -> Unit,
    home: String, away: String,
    homeCrest: String?, awayCrest: String?,
    meta: String,
) {
    Column(
        Modifier.fillMaxWidth().statusBarsPadding().padding(16.dp, 10.dp, 16.dp, 16.dp)
    ) {
        Text("‹  GERİ", style = com.ahmet.edge.ui.theme.LabelMono, color = Ink.muted,
            modifier = Modifier.clip(RoundedCornerShape(4.dp))
                .clickable(onClick = onBack).padding(vertical = 6.dp, horizontal = 2.dp))
        Spacer(Modifier.height(14.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TeamCrest(homeCrest, home, 30.dp)
                    Spacer(Modifier.width(10.dp))
                    Text(home, style = MaterialTheme.typography.titleLarge, color = Ink.text,
                        maxLines = 1)
                }
                Spacer(Modifier.height(9.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TeamCrest(awayCrest, away, 30.dp)
                    Spacer(Modifier.width(10.dp))
                    Text(away, style = MaterialTheme.typography.titleLarge, color = Ink.text,
                        maxLines = 1)
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(meta, style = com.ahmet.edge.ui.theme.LabelMono.copy(fontSize = 10.sp),
            color = Ink.faint)
    }
    Hairline()
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        SectionLabel(title)
        Panel(padding = PaddingValues(14.dp)) { content() }
    }
}

@Composable
private fun MarketLine(label: String, prob: Double?) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp),
        horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Ink.text, style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(prob?.let { pct(it) } ?: "—", color = Ink.muted,
                style = MaterialTheme.typography.bodyMedium)
            Text(prob?.let { fmt(1.0 / it) } ?: "—", color = Ink.text,
                style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun QuotaWall(e: AppError.QuotaExceeded, onUpgrade: () -> Unit, modifier: Modifier) {
    Column(modifier.fillMaxWidth().background(Ink.caution.copy(alpha = 0.08f))
        .padding(16.dp)) {
        Text("Günlük ${e.limit} analiz hakkın doldu",
            style = MaterialTheme.typography.titleMedium, color = Ink.text)
        Text("Yarın sıfırlanır. Sınırsız analiz için aboneliğe geçebilirsin.",
            style = MaterialTheme.typography.bodySmall, color = Ink.muted)
        TextButton(onUpgrade) { Text("Planları gör", color = Ink.brass) }
    }
}

private fun labelOf(sel: String) = when (sel) {
    "HOME" -> "1"; "DRAW" -> "X"; "AWAY" -> "2"; else -> sel
}

private val dateFmt: DateTimeFormatter =
    DateTimeFormatter.ofPattern("d MMM · HH:mm")

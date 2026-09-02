package com.ahmet.edge.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
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
    val summary by vm.summary.collectAsState()
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
                "${it.league.name.uppercase(java.util.Locale.ROOT)} · " +
                    dateFmt.format(it.kickoff.atZone(ZoneId.systemDefault()))
            } ?: ""
        )

        (ui.error as? AppError.QuotaExceeded)?.let { QuotaWall(it, onUpgrade, Modifier) }

        LazyColumn(
            Modifier.fillMaxSize().navigationBarsPadding(),
            contentPadding = PaddingValues(16.dp, 14.dp, 16.dp, 32.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            // ---- Yapay zeka maç analizi -------------------------------
            (summary?.live ?: summary?.summary)?.let { txt ->
                item {
                    val isLive = summary?.live != null
                    Column(Modifier.fillMaxWidth()) {
                        SectionLabel(if (isLive) "Canlı analiz" else "Maç analizi")
                        Column(
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp))
                                .background(if (isLive) Ink.live.copy(alpha = 0.08f) else Ink.surface)
                                .border(
                                    1.dp,
                                    if (isLive) Ink.live.copy(alpha = 0.4f) else Ink.line,
                                    RoundedCornerShape(6.dp)
                                )
                                .padding(14.dp)
                        ) {
                            Text(txt, style = MaterialTheme.typography.bodyMedium, color = Ink.text)
                        }
                    }
                }
            }

            // ---- Model projeksiyonu ------------------------------------
            m?.let { mm ->
                item {
                    Section("Model tahmini") {
                        val p = ui.probs1x2
                        val ph = p["HOME"] ?: .34; val pd = p["DRAW"] ?: .33; val pa = p["AWAY"] ?: .33
                        val pick = when (maxOf(ph, pd, pa)) { ph -> 0; pd -> 1; else -> 2 }
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                            ScoreCol("1", ph, pick == 0)
                            ScoreCol("X", pd, pick == 1)
                            ScoreCol("2", pa, pick == 2)
                        }
                        Spacer(Modifier.height(14.dp))
                        ProbBar3(ph, pd, pa, height = 5.dp)
                        Spacer(Modifier.height(12.dp))
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
                            StatCell("BEK. GOL EV", fmt(mm.lambdaHome ?: 0.0), Ink.text)
                            StatCell("BEK. GOL DEP", fmt(mm.lambdaAway ?: 0.0), Ink.text)
                            StatCell("GÜVEN", pct0(mm.modelConfidence), Ink.muted)
                        }
                    }
                }
            }

            // ---- Skor dağılımı ---------------------------------------
            m?.let { mm ->
                item {
                    val mat = remember(mm.id, mm.lambdaHome, mm.lambdaAway) {
                        com.ahmet.edge.domain.engine.PoissonMath.scoreMatrix(
                            mm.lambdaHome ?: 1.35, mm.lambdaAway ?: 1.10, mm.rho)
                    }
                    Column(Modifier.fillMaxWidth()) {
                        SectionLabel("Skor dağılımı")
                        Panel(padding = PaddingValues(14.dp)) {
                            com.ahmet.edge.ui.component.ScoreGrid(mat)
                        }
                    }
                }
            }

            // ---- Oranını gir -> canlı edge/Kelly ----------------------
            item {
                OddsEntryCard(
                    fair = mapOf(
                        "1" to (ui.probs1x2["HOME"]?.let { if (it > 0) 1.0 / it else 0.0 } ?: 0.0),
                        "X" to (ui.probs1x2["DRAW"]?.let { if (it > 0) 1.0 / it else 0.0 } ?: 0.0),
                        "2" to (ui.probs1x2["AWAY"]?.let { if (it > 0) 1.0 / it else 0.0 } ?: 0.0),
                    ),
                    onCompute = { h, d, a -> vm.setManualOdds(h, d, a) }
                )
            }

            // ---- Maç sonucu olasılığı (oran girildiyse edge ile) ------
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
                        Text("Girilen oranların marjı ${pct(ui.marginPct)} — adil oran bu çıkarıldıktan sonra.",
                            style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                    }
                }
            }

            // ---- PRO: değer tespiti -------------------------------------
            item {
                if (ent.allows(Feature.EDGE_DETECTION)) {
                    Section("Kenar payı") {
                        if (ui.edges.isEmpty()) {
                            Text("Yukarıdan oranını gir — modelin olasılığı ile senin " +
                                "oranının ima ettiği olasılık karşılaştırılsın.",
                                style = MaterialTheme.typography.bodyMedium, color = Ink.muted)
                        } else {
                            ui.edges.sortedByDescending { it.edgePct }.forEachIndexed { idx, e ->
                                // yeşil sadece gerçek değerde; sert ayrışma nötr, negatif kırmızı
                                val kenarTint = when {
                                    e.isValue -> Ink.signal
                                    e.edgePct < 0 -> Ink.caution
                                    else -> Ink.muted
                                }
                                if (idx > 0) Hairline()
                                Column(Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(labelOf(e.selection), Modifier.width(26.dp),
                                            style = MaterialTheme.typography.titleMedium,
                                            color = Ink.text)
                                        StatCell("KENAR", signedPct(e.edgePct),
                                            kenarTint, Modifier.weight(1f))
                                        StatCell("ORAN", fmt(e.takenPrice), Ink.text, Modifier.weight(1f))
                                        StatCell("GÜVEN", when (e.confidence) {
                                            Confidence.HIGH -> "YÜKSEK"; Confidence.MEDIUM -> "ORTA"
                                            Confidence.LOW -> "DÜŞÜK"
                                        }, Ink.muted, Modifier.weight(1f))
                                    }
                                    Spacer(Modifier.height(8.dp))
                                    Row(Modifier.padding(start = 26.dp),
                                        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                        ActionChip("+ KUPON", Ink.muted) {
                                            vm.addToCoupon(e.selection, labelOf(e.selection),
                                                e.modelProb, e.takenPrice)
                                        }
                                        if (e.isValue) ActionChip("KAYDET", Ink.accent) { recording = e }
                                    }
                                }
                            }
                            Spacer(Modifier.height(4.dp))
                            Text("Pozitif kenar = model bu sonucu senin oranının ima " +
                                "ettiğinden daha olası görüyor. Garanti değil.",
                                style = MaterialTheme.typography.bodySmall, color = Ink.faint)
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
                    val chartSel by vm.selectedForChart.collectAsState()
                    Section("Oran hareketi") {
                        Row(
                            Modifier.clip(RoundedCornerShape(5.dp))
                                .border(1.dp, Ink.line, RoundedCornerShape(5.dp))
                        ) {
                            listOf("HOME" to "1", "DRAW" to "X", "AWAY" to "2")
                                .forEach { (key, label) ->
                                    val on = chartSel == key
                                    Box(
                                        Modifier.weight(1f)
                                            .background(if (on) Ink.accentDim else Color.Transparent)
                                            .clickable { vm.selectForChart(key) }
                                            .padding(vertical = 8.dp),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(label, style = MaterialTheme.typography.labelMedium,
                                            color = if (on) Ink.accent else Ink.muted)
                                    }
                                }
                        }
                        Spacer(Modifier.height(10.dp))
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
    val root = java.util.Locale.ROOT
    val hColor = com.ahmet.edge.ui.theme.TeamStyle.color(home)
    val aColor = com.ahmet.edge.ui.theme.TeamStyle.color(away)
    Column(
        Modifier.fillMaxWidth()
            .background(
                androidx.compose.ui.graphics.Brush.verticalGradient(
                    listOf(hColor.copy(alpha = 0.24f), Ink.surface)
                )
            )
            .statusBarsPadding()
            .padding(16.dp, 10.dp, 16.dp, 18.dp)
    ) {
        Text("‹  MAÇLAR", style = com.ahmet.edge.ui.theme.LabelMono, color = Ink.muted,
            modifier = Modifier.clip(RoundedCornerShape(4.dp))
                .clickable(onClick = onBack).padding(vertical = 6.dp, horizontal = 2.dp))
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Crest(com.ahmet.edge.ui.theme.TeamStyle.code(home), hColor, 46.dp)
                Spacer(Modifier.height(9.dp))
                Text(home.uppercase(root), style = MaterialTheme.typography.titleMedium,
                    color = Ink.text,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center, maxLines = 2)
            }
            Text("VS", style = MaterialTheme.typography.titleLarge, color = Ink.faint,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 14.dp))
            Column(Modifier.weight(1f),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Crest(com.ahmet.edge.ui.theme.TeamStyle.code(away), aColor, 46.dp)
                Spacer(Modifier.height(9.dp))
                Text(away.uppercase(root), style = MaterialTheme.typography.titleMedium,
                    color = Ink.text,
                    textAlign = androidx.compose.ui.text.style.TextAlign.Center, maxLines = 2)
            }
        }
        Spacer(Modifier.height(14.dp))
        Text(meta.uppercase(root),
            style = com.ahmet.edge.ui.theme.LabelMono.copy(fontSize = 10.sp), color = Ink.faint,
            modifier = Modifier.align(Alignment.CenterHorizontally))
    }
    Hairline()
}

@Composable
private fun ScoreCol(k: String, v: Double, pick: Boolean) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(k, style = com.ahmet.edge.ui.theme.LabelMono.copy(fontSize = 12.sp, letterSpacing = 2.sp),
            color = if (pick) Ink.accent else Ink.faint)
        Spacer(Modifier.height(7.dp))
        Text("${(v * 100).toInt()}",
            style = MaterialTheme.typography.displaySmall,
            color = if (pick) Ink.text else Ink.muted)
    }
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        SectionLabel(title)
        Panel(padding = PaddingValues(14.dp)) { content() }
    }
}

@Composable
private fun OddsEntryCard(fair: Map<String, Double>, onCompute: (Double, Double, Double) -> Unit) {
    var h by remember { mutableStateOf("") }
    var d by remember { mutableStateOf("") }
    var a by remember { mutableStateOf("") }
    val hv = h.replace(',', '.').toDoubleOrNull()
    val dv = d.replace(',', '.').toDoubleOrNull()
    val av = a.replace(',', '.').toDoubleOrNull()
    val ready = (hv ?: 0.0) > 1.0 && (dv ?: 0.0) > 1.0 && (av ?: 0.0) > 1.0

    Column(Modifier.fillMaxWidth()) {
        SectionLabel("Oranını gir")
        Panel(padding = PaddingValues(14.dp)) {
            Text("Kendi bahisçinde gördüğün 1 / X / 2 oranını yaz — model kenar payını " +
                "ve önerilen tutarı ona göre hesaplar.",
                style = MaterialTheme.typography.bodySmall, color = Ink.muted)
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                OddsField("1", h, fair["1"]) { h = it }
                OddsField("X", d, fair["X"]) { d = it }
                OddsField("2", a, fair["2"]) { a = it }
            }
            Spacer(Modifier.height(12.dp))
            if (ready) {
                PrimaryButton("Hesapla", onClick = { onCompute(hv!!, dv!!, av!!) })
            } else {
                Text("Üç oranı da gir", style = com.ahmet.edge.ui.theme.LabelMono,
                    color = Ink.faint, modifier = Modifier.padding(vertical = 4.dp))
            }
        }
    }
}

@Composable
private fun OddsField(label: String, value: String, fair: Double?, onChange: (String) -> Unit) {
    Column(Modifier.width(96.dp)) {
        Row {
            Text(label, style = com.ahmet.edge.ui.theme.LabelMono, color = Ink.faint)
            if (fair != null && fair > 1.0) {
                Spacer(Modifier.weight(1f))
                Text("adil ${fmt(fair)}", style = com.ahmet.edge.ui.theme.LabelMono
                    .copy(fontSize = 9.sp), color = Ink.faint)
            }
        }
        Spacer(Modifier.height(4.dp))
        androidx.compose.foundation.text.BasicTextField(
            value = value,
            onValueChange = { s -> onChange(s.filter { it.isDigit() || it == '.' || it == ',' }.take(5)) },
            singleLine = true,
            textStyle = com.ahmet.edge.ui.theme.DataStyle.copy(
                fontSize = 16.sp, color = Ink.text),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(Ink.accent),
            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                keyboardType = androidx.compose.ui.text.input.KeyboardType.Decimal),
            decorationBox = { inner ->
                Box(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(5.dp))
                        .background(Ink.raised).border(1.dp, Ink.lineStrong, RoundedCornerShape(5.dp))
                        .padding(horizontal = 10.dp, vertical = 9.dp)
                ) {
                    if (value.isEmpty()) Text("—", style = com.ahmet.edge.ui.theme.DataStyle
                        .copy(fontSize = 16.sp), color = Ink.faint)
                    inner()
                }
            }
        )
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

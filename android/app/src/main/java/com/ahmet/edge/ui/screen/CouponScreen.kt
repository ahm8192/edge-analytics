package com.ahmet.edge.ui.screen

import androidx.compose.foundation.background
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
import com.ahmet.edge.domain.CouponPick
import com.ahmet.edge.domain.CouponStore
import com.ahmet.edge.ui.component.*
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

@HiltViewModel
class CouponViewModel @Inject constructor(val store: CouponStore) : ViewModel()

@Composable
fun CouponScreen(onBack: () -> Unit, onOpenMatch: (Long) -> Unit,
                 vm: CouponViewModel = hiltViewModel()) {
    val picks by vm.store.picks.collectAsState()
    val a = remember(picks) { vm.store.analyze(picks) }

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        Column(Modifier.fillMaxWidth().statusBarsPadding().padding(16.dp, 10.dp, 16.dp, 14.dp)) {
            Text("‹  GERİ", style = LabelMono, color = Ink.muted,
                modifier = Modifier.clip(RoundedCornerShape(4.dp)).clickable(onClick = onBack)
                    .padding(vertical = 6.dp, horizontal = 2.dp))
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Kupon analizi", style = MaterialTheme.typography.headlineSmall,
                    color = Ink.text, modifier = Modifier.weight(1f))
                if (picks.isNotEmpty())
                    Text("TEMİZLE", style = LabelMono, color = Ink.caution,
                        modifier = Modifier.clip(RoundedCornerShape(4.dp))
                            .clickable { vm.store.clear() }.padding(6.dp))
            }
        }
        Hairline()

        if (picks.isEmpty()) {
            EmptyState("Kupon boş",
                "Maç detayında bir seçimin yanındaki '+' ile kupona ekle. En az 2 seçim gerekir.")
            return
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 12.dp, 16.dp, 32.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp)
        ) {
            item {
                Panel {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        StatCell("SEÇİM", picks.size.toString(), Ink.text)
                        StatCell("MODEL OLASILIK", pct(a.combinedProb), Ink.text)
                        StatCell("ORAN", fmt(a.combinedOdds), Ink.text)
                    }
                    Spacer(Modifier.height(12.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        StatCell("ADİL ORAN", fmt(a.fairOdds), Ink.muted)
                        StatCell("KENAR PAYI", signedPct(a.edgePct),
                            if (a.edgePct > 0) Ink.signal else Ink.caution)
                        if (a.hasValue) EdgeTag(a.edgePct)
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(
                        when {
                            a.sameMatch -> "Aynı maçtan iki seçim var — bunlar korelasyonlu, " +
                                "birleşik olasılık gerçekte bundan farklı. Kombine için ayrı maçlar seç."
                            a.picks.size < 2 -> "En az 2 seçim ekle."
                            a.edgePct > 0 -> "Model bu kombinasyonu oranın ima ettiğinden daha " +
                                "olası görüyor. Kombine varyansı tekli bahisten çok daha yüksektir."
                            else -> "Model bu kombinasyonda kenar görmüyor. Kombine, marjı " +
                                "katladığı için genelde tekliden kötüdür."
                        },
                        style = MaterialTheme.typography.bodySmall, color = Ink.muted
                    )
                }
            }
            items(picks, key = { it.matchId.toString() + it.market }) { p ->
                PickRow(p, onOpen = { onOpenMatch(p.matchId) },
                    onRemove = { vm.store.remove(p.matchId, p.market) })
            }
        }
    }
}

@Composable
private fun PickRow(p: CouponPick, onOpen: () -> Unit, onRemove: () -> Unit) {
    Panel(onClick = onOpen, padding = PaddingValues(14.dp, 11.dp, 10.dp, 11.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(p.label, style = MaterialTheme.typography.titleMedium, color = Ink.text,
                    maxLines = 1, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(3.dp))
                Text("${p.market} · ${p.selectionLabel} · model ${pct(p.modelProb)} · @ ${fmt(p.price)}",
                    style = LabelMono.copy(fontSize = 10.sp), color = Ink.muted)
            }
            Text("×", style = MaterialTheme.typography.headlineSmall, color = Ink.faint,
                modifier = Modifier.clip(RoundedCornerShape(4.dp)).clickable(onClick = onRemove)
                    .padding(horizontal = 10.dp, vertical = 4.dp))
        }
    }
}

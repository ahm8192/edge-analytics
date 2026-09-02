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
import androidx.lifecycle.viewModelScope
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.LocalEntitlement
import com.ahmet.edge.data.repo.BettingRepository
import com.ahmet.edge.domain.model.Bet
import com.ahmet.edge.domain.model.BetOutcome
import com.ahmet.edge.ui.component.*
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import javax.inject.Inject

@HiltViewModel
class BetLogViewModel @Inject constructor(
    private val repo: BettingRepository
) : ViewModel() {
    val bets = repo.observeBets()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun settle(betId: Long, outcome: BetOutcome) =
        viewModelScope.launch { repo.settle(betId, outcome) }
}

@Composable
fun BetLogScreen(onUpgrade: () -> Unit, vm: BetLogViewModel = hiltViewModel()) {
    val ent = LocalEntitlement.current
    val bets by vm.bets.collectAsState()

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        ScreenHeader(
            "Günlük",
            right = if (bets.isNotEmpty()) "${bets.count { it.outcome == BetOutcome.OPEN }} AÇIK" else null,
            sub = "Oynamadıkların da kayıtlı — model denetimi onlarsız eksik kalır."
        )

        if (!ent.allows(Feature.BET_LOG)) {
            LockedFeaturePane(
                "Bahis günlüğü · PRO",
                "Her tahmin (oynasan da oynamasan da) kaydedilir; biten maçlar otomatik " +
                    "sonuçlanır. Model gerçekten işe yarıyor mu, ancak bu kayıtla görürsün.",
                onUpgrade
            )
            return
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 10.dp, 16.dp, 40.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp)
        ) {
            items(bets, key = { it.id }) { bet ->
                BetRow(bet) { outcome -> vm.settle(bet.id, outcome) }
            }
            if (bets.isEmpty()) item {
                EmptyState("Henüz kayıt yok",
                    "Bir maça girip kenar payı olan seçimi 'Kaydet' ile buraya ekle.")
            }
        }
    }
}

@Composable
private fun BetRow(b: Bet, onSettle: (BetOutcome) -> Unit) {
    var settling by remember { mutableStateOf(false) }
    if (settling) SettleBetDialog(
        matchLabel = b.matchLabel, selection = b.selection,
        stake = b.stake, price = b.takenPrice,
        onDismiss = { settling = false },
        onSettle = { outcome -> onSettle(BetOutcome.valueOf(outcome)); settling = false }
    )

    val oc = b.outcome
    Panel(padding = PaddingValues(14.dp, 12.dp, 14.dp, 12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(b.matchLabel, style = MaterialTheme.typography.titleMedium, color = Ink.text,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (oc == BetOutcome.OPEN) {
                Text("SONUÇLANDIR", style = LabelMono, color = Ink.accent,
                    modifier = Modifier.clip(RoundedCornerShape(4.dp))
                        .clickable { settling = true }
                        .padding(horizontal = 8.dp, vertical = 6.dp))
            } else {
                val (txt, c) = when (oc) {
                    BetOutcome.WIN -> "KAZANDI" to Ink.signal
                    BetOutcome.LOSE -> "KAYBETTİ" to Ink.caution
                    BetOutcome.PUSH -> "İADE" to Ink.muted
                    BetOutcome.VOID -> "İPTAL" to Ink.muted
                    BetOutcome.OPEN -> "" to Ink.faint
                }
                Tag(txt, c)
            }
        }
        Spacer(Modifier.height(4.dp))
        Text("${b.market} · ${b.selection} @ ${fmt(b.takenPrice)}",
            style = LabelMono.copy(fontSize = 10.sp), color = Ink.muted)
        Spacer(Modifier.height(11.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            StatCell("TUTAR", if (b.wasPlaced) fmt(b.stake) else "KÂĞIT", Ink.text)
            StatCell("MODEL", pct(b.modelProb), Ink.text)
            StatCell("CLV", b.clvPct?.let { signedPct(it) } ?: "—",
                if ((b.clvPct ?: 0.0) >= 0) Ink.signal else Ink.caution)
            StatCell("SONUÇ", b.pnl?.let { fmt(it) } ?: "—",
                if ((b.pnl ?: 0.0) >= 0) Ink.signal else Ink.caution)
        }
        Spacer(Modifier.height(8.dp))
        Text(logFmt.format(b.placedAt.atZone(ZoneId.systemDefault())),
            style = LabelMono.copy(fontSize = 9.sp), color = Ink.faint)
    }
}

private val logFmt: DateTimeFormatter =
    DateTimeFormatter.ofPattern("d MMM · HH:mm", Locale("tr"))

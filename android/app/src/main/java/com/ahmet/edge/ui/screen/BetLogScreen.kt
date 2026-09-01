package com.ahmet.edge.ui.screen

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
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
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.ZoneId
import java.time.format.DateTimeFormatter
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

    if (!ent.allows(Feature.BET_LOG)) {
        Column(Modifier.fillMaxSize().padding(16.dp)) {
            Text("Günlük", style = MaterialTheme.typography.headlineSmall, color = Ink.text)
            Spacer(Modifier.height(16.dp))
            LockedCard(Feature.BET_LOG, onUpgrade)
            Spacer(Modifier.height(12.dp))
            Text("Oynadıklarını kaydetmezsen modelin işe yarayıp yaramadığını " +
                 "asla bilemezsin. Hafıza seçicidir, günlük değildir.",
                style = MaterialTheme.typography.bodySmall, color = Ink.faint)
        }
        return
    }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Column {
                Text("Günlük", style = MaterialTheme.typography.headlineSmall, color = Ink.text)
                Text("Oynamadıkların da kayıtlı — denetim onlarsız eksik kalır.",
                    style = MaterialTheme.typography.bodySmall, color = Ink.muted)
            }
        }
        items(bets, key = { it.id }) { bet ->
            BetRow(bet, onSettle = { outcome -> vm.settle(bet.id, outcome) })
        }
        if (bets.isEmpty()) item {
            Text("Henüz kayıt yok.", color = Ink.faint,
                modifier = Modifier.padding(vertical = 40.dp))
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
        onSettle = { outcome ->
            onSettle(BetOutcome.valueOf(outcome)); settling = false
        }
    )

    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(10.dp), color = Ink.surface) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text(b.matchLabel, color = Ink.text,
                        style = MaterialTheme.typography.titleMedium)
                    Text("${b.market} · ${b.selection} @ ${fmt(b.takenPrice)}",
                        color = Ink.muted, style = MaterialTheme.typography.bodySmall)
                }
                if (b.outcome == BetOutcome.OPEN) {
                    TextButton(onClick = { settling = true }) {
                        Text("Sonuçlandır", color = Ink.signal,
                            style = MaterialTheme.typography.labelMedium)
                    }
                } else Text(
                    when (b.outcome) {
                        BetOutcome.OPEN -> "açık"
                        BetOutcome.WIN -> "kazandı"
                        BetOutcome.LOSE -> "kaybetti"
                        BetOutcome.PUSH -> "iade"
                        BetOutcome.VOID -> "iptal"
                    },
                    color = when (b.outcome) {
                        BetOutcome.WIN -> Ink.signal
                        BetOutcome.LOSE -> Ink.caution
                        else -> Ink.faint
                    },
                    style = MaterialTheme.typography.labelMedium
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(22.dp)) {
                StatChip("tutar", if (b.wasPlaced) fmt(b.stake) else "kağıt")
                StatChip("model", pct(b.modelProb))
                b.clvPct?.let {
                    StatChip("CLV", signedPct(it), if (it >= 0) Ink.signal else Ink.caution)
                }
                b.pnl?.let {
                    StatChip("sonuç", fmt(it), if (it >= 0) Ink.signal else Ink.caution)
                }
            }
            Text(logFmt.format(b.placedAt.atZone(ZoneId.systemDefault())),
                color = Ink.faint, style = MaterialTheme.typography.bodySmall)
        }
    }
}

private val logFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("d MMM yyyy · HH:mm")

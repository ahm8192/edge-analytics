package com.ahmet.edge.ui.screen

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.LocalEntitlement
import com.ahmet.edge.data.local.MarketPerformance
import com.ahmet.edge.data.repo.*
import com.ahmet.edge.domain.model.Bankroll
import com.ahmet.edge.ui.component.*
import com.ahmet.edge.ui.theme.Ink
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class BankrollViewModel @Inject constructor(
    private val repo: BettingRepository
) : ViewModel() {
    val bankroll = repo.observeBankroll()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000),
                 Bankroll(0.0, 0.0, 0.0, 0.0))

    val clv = repo.observeBets().map { it.clvSummary() }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000),
                 ClvSummary(0, 0.0, 0.0, 0.0, false, 0.0))

    val byMarket = repo.observePerformance()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    fun setStarting(amount: Double) = viewModelScope.launch { repo.setBankroll(amount) }
}

@Composable
fun BankrollScreen(onUpgrade: () -> Unit, vm: BankrollViewModel = hiltViewModel()) {
    val ent = LocalEntitlement.current
    val b by vm.bankroll.collectAsState()
    val clv by vm.clv.collectAsState()
    val byMarket by vm.byMarket.collectAsState()

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()
        .verticalScroll(rememberScrollState()).padding(16.dp, 12.dp, 16.dp, 32.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)) {

        Text("Kasa", style = MaterialTheme.typography.headlineSmall, color = Ink.text)

        if (!ent.allows(Feature.BANKROLL_MANAGER)) {
            LockedCard(Feature.BANKROLL_MANAGER, onUpgrade)
            LockedCard(Feature.CLV_TRACKING, onUpgrade)
            return@Column
        }

        Surface(shape = RoundedCornerShape(12.dp), color = Ink.surface) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(fmt(b.current), style = MaterialTheme.typography.displaySmall,
                    color = Ink.text)
                Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                    StatChip("kâr/zarar", fmt(b.pnl),
                        if (b.pnl >= 0) Ink.signal else Ink.caution)
                    StatChip("getiri", signedPct(b.roi),
                        if (b.roi >= 0) Ink.signal else Ink.caution)
                    StatChip("açık risk", fmt(b.openExposure))
                }
                if (b.drawdown > 0.10) {
                    Text("Zirveden ${pct(b.drawdown)} gerideisin. " +
                         "%20-30 düşüşler pozitif beklentili sistemlerde bile olağandır; " +
                         "tutarları büyütmek için sebep değildir.",
                        style = MaterialTheme.typography.bodySmall, color = Ink.caution)
                }
            }
        }

        // --- CLV: asıl karne ---------------------------------------------
        Column {
            Text("Kapanış oranı karnesi", style = MaterialTheme.typography.titleMedium,
                color = Ink.text)
            Spacer(Modifier.height(4.dp))
            Text("Kâr şansa bağlıdır; kapanış oranını yenmek değildir.",
                style = MaterialTheme.typography.bodySmall, color = Ink.faint)
            Spacer(Modifier.height(12.dp))
            Surface(shape = RoundedCornerShape(12.dp), color = Ink.surface) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(28.dp)) {
                        StatChip("bahis", clv.n.toString())
                        StatChip("ort. CLV", signedPct(clv.meanClv),
                            if (clv.meanClv >= 0) Ink.signal else Ink.caution)
                        StatChip("kapanışı yenme", pct(clv.beatCloseRate))
                    }
                    Text(clv.verdict, style = MaterialTheme.typography.bodyMedium,
                        color = Ink.muted)
                }
            }
        }

        // --- ELITE: segment dökümü ---------------------------------------
        if (ent.allows(Feature.PORTFOLIO_BREAKDOWN)) {
            Column {
                Text("Market bazında", style = MaterialTheme.typography.titleMedium,
                    color = Ink.text)
                Spacer(Modifier.height(10.dp))
                byMarket.forEach { p -> MarketPerfRow(p) }
                if (byMarket.isEmpty())
                    Text("Sonuçlanmış bahis yok.", color = Ink.faint,
                        style = MaterialTheme.typography.bodySmall)
            }
        } else LockedCard(Feature.PORTFOLIO_BREAKDOWN, onUpgrade)
    }
}

@Composable
private fun MarketPerfRow(p: MarketPerformance) {
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.SpaceBetween) {
        Text(p.market, color = Ink.text, style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
            Text("${p.n}", color = Ink.faint, style = MaterialTheme.typography.bodySmall)
            Text(signedPct(p.roi), style = MaterialTheme.typography.bodyMedium,
                color = if (p.roi >= 0) Ink.signal else Ink.caution)
            Text(p.meanClv?.let { signedPct(it) } ?: "—", color = Ink.muted,
                style = MaterialTheme.typography.bodyMedium)
        }
    }
}

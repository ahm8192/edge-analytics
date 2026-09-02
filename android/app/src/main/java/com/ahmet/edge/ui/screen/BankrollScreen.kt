package com.ahmet.edge.ui.screen

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.LocalEntitlement
import com.ahmet.edge.data.local.MarketPerformance
import com.ahmet.edge.data.repo.*
import com.ahmet.edge.domain.model.Bankroll
import com.ahmet.edge.ui.component.*
import com.ahmet.edge.ui.theme.DataStyle
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono
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
    var editing by remember(b.starting) { mutableStateOf(b.starting <= 0.0) }

    Column(Modifier.fillMaxSize().background(Ink.base)) {
        ScreenHeader("Kasa", right = if (b.starting > 0) "BAŞLANGIÇ ${fmt(b.starting)}" else null)

        if (!ent.allows(Feature.BANKROLL_MANAGER)) {
            LockedFeaturePane(
                "Kasa yönetimi · PRO",
                "Açık riskini, kâr-zararını, düşüş oranını ve asıl önemlisi kapanış " +
                    "oranını yenip yenmediğini (CLV) takip eder.",
                onUpgrade
            )
            return
        }

        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp, 12.dp, 16.dp, 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            if (editing || b.starting <= 0.0) item {
                var txt by remember { mutableStateOf(if (b.starting > 0) b.starting.toInt().toString() else "") }
                val amt = txt.toDoubleOrNull() ?: 0.0
                Panel {
                    SectionLabel("Başlangıç kasası")
                    Text("Kelly tutar önerileri ve getiri hesabı buna göre yapılır.",
                        style = MaterialTheme.typography.bodySmall, color = Ink.muted)
                    Spacer(Modifier.height(12.dp))
                    BasicTextField(
                        value = txt,
                        onValueChange = { s -> txt = s.filter { it.isDigit() }.take(9) },
                        singleLine = true,
                        textStyle = DataStyle.copy(fontSize = 22.sp, color = Ink.text),
                        cursorBrush = SolidColor(Ink.accent),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        decorationBox = { inner ->
                            Box(
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp))
                                    .background(Ink.raised)
                                    .border(1.dp, Ink.lineStrong, RoundedCornerShape(6.dp))
                                    .padding(horizontal = 14.dp, vertical = 12.dp)
                            ) {
                                if (txt.isEmpty()) Text("örn. 1000",
                                    style = DataStyle.copy(fontSize = 22.sp), color = Ink.faint)
                                inner()
                            }
                        }
                    )
                    Spacer(Modifier.height(12.dp))
                    if (amt > 0) PrimaryButton("Kaydet", { vm.setStarting(amt); editing = false })
                    else Text("Bir tutar gir", style = LabelMono, color = Ink.faint)
                }
            }

            // --- bakiye
            item {
                Panel {
                    Text(fmt(b.current), style = MaterialTheme.typography.displaySmall, color = Ink.text)
                    Spacer(Modifier.height(12.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        StatCell("KÂR / ZARAR", fmt(b.pnl),
                            if (b.pnl >= 0) Ink.signal else Ink.caution)
                        StatCell("GETİRİ", signedPct(b.roi),
                            if (b.roi >= 0) Ink.signal else Ink.caution)
                        StatCell("AÇIK RİSK", fmt(b.openExposure), Ink.text)
                    }
                    if (b.starting > 0 && !editing) {
                        Spacer(Modifier.height(12.dp))
                        Text("BAŞLANGICI DEĞİŞTİR", style = LabelMono, color = Ink.accent,
                            modifier = Modifier
                                .clip(RoundedCornerShape(3.dp))
                                .clickable { editing = true }
                                .padding(vertical = 4.dp)
                        )
                    }
                    if (b.drawdown > 0.10) {
                        Spacer(Modifier.height(10.dp))
                        Text("Zirveden ${pct(b.drawdown)} geridesin. %20-30 düşüşler pozitif " +
                            "beklentili sistemlerde bile olağan; tutar büyütmek için sebep değil.",
                            style = MaterialTheme.typography.bodySmall, color = Ink.caution)
                    }
                }
            }

            // --- CLV karne
            item {
                Column {
                    SectionLabel("Kapanış oranı karnesi")
                    Panel {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            StatCell("BAHİS", clv.n.toString(), Ink.text)
                            StatCell("ORT. CLV", signedPct(clv.meanClv),
                                if (clv.meanClv >= 0) Ink.signal else Ink.caution)
                            StatCell("KAPANIŞI YENME", pct(clv.beatCloseRate), Ink.text)
                        }
                        Spacer(Modifier.height(10.dp))
                        Text(clv.verdict, style = MaterialTheme.typography.bodyMedium, color = Ink.muted)
                        Spacer(Modifier.height(4.dp))
                        Text("Kâr şansa bağlıdır; kapanış oranını yenmek sistemin çalıştığını gösterir.",
                            style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                    }
                }
            }

            // --- ELITE market dökümü
            item {
                if (ent.allows(Feature.PORTFOLIO_BREAKDOWN)) {
                    Column {
                        SectionLabel("Market bazında")
                        Panel {
                            if (byMarket.isEmpty()) Text("Sonuçlanmış bahis yok.",
                                style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                            byMarket.forEachIndexed { i, p ->
                                if (i > 0) Hairline()
                                MarketPerfRow(p)
                            }
                        }
                    }
                } else LockedCard(Feature.PORTFOLIO_BREAKDOWN, onUpgrade)
            }
        }
    }
}

@Composable
private fun MarketPerfRow(p: MarketPerformance) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(p.market, style = MaterialTheme.typography.titleMedium, color = Ink.text,
            modifier = Modifier.weight(1f))
        StatCell("N", "${p.n}", Ink.muted, Modifier.width(50.dp))
        StatCell("ROI", signedPct(p.roi),
            if (p.roi >= 0) Ink.signal else Ink.caution, Modifier.width(72.dp))
        StatCell("CLV", p.meanClv?.let { signedPct(it) } ?: "—", Ink.muted, Modifier.width(72.dp))
    }
}

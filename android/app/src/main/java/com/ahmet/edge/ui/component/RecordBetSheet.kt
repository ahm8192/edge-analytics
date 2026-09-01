package com.ahmet.edge.ui.component

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.ahmet.edge.domain.engine.Kelly
import com.ahmet.edge.domain.engine.StakeResult
import com.ahmet.edge.ui.theme.Ink

/**
 * Bahis kaydetme.
 *
 * İki ayrı düğme var çünkü ikisi ayrı şey: "oynadım" ve "oynamadım ama
 * modelin ne dediğini kaydet". İkincisi olmadan model denetimi seçici hafızaya
 * dönüşür — insan kazandıklarını hatırlar, geçtiklerini unutur.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RecordBetSheet(
    matchLabel: String,
    selection: String,
    modelProb: Double,
    suggestedPrice: Double,
    suggestedStake: StakeResult?,
    bankroll: Double,
    recentOutcomes: List<String>,
    averageStake: Double,
    onDismiss: () -> Unit,
    onConfirm: (price: Double, stake: Double, actuallyPlaced: Boolean) -> Unit
) {
    var priceText by remember { mutableStateOf(fmt(suggestedPrice)) }
    var stakeText by remember {
        mutableStateOf(suggestedStake?.takeIf { !it.skipped }?.let { fmt(it.stake) } ?: "")
    }

    val price = priceText.replace(',', '.').toDoubleOrNull()
    val stake = stakeText.replace(',', '.').toDoubleOrNull()

    // Girilen fiyata göre kenar payı canlı yeniden hesaplanır — kullanıcı
    // aldığı gerçek oranı yazınca değer kaybolmuş olabilir.
    val liveEdge = price?.let { modelProb * it - 1.0 }
    val martingale = if (stake != null)
        Kelly.martingaleWarning(recentOutcomes, stake, averageStake) else null

    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Ink.surface) {
        Column(
            Modifier.padding(horizontal = 20.dp).padding(bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Column {
                Text("Kaydet", style = MaterialTheme.typography.headlineSmall,
                    color = Ink.text)
                Text("$matchLabel · $selection",
                    style = MaterialTheme.typography.bodyMedium, color = Ink.muted)
            }

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = priceText, onValueChange = { priceText = it },
                    label = { Text("Aldığın oran") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true, modifier = Modifier.weight(1f),
                    colors = fieldColors()
                )
                OutlinedTextField(
                    value = stakeText, onValueChange = { stakeText = it },
                    label = { Text("Tutar") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true, modifier = Modifier.weight(1f),
                    colors = fieldColors()
                )
            }

            Surface(shape = RoundedCornerShape(10.dp), color = Ink.raised,
                modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(26.dp)) {
                        StatChip("model", pct(modelProb))
                        StatChip("adil oran", fmt(1.0 / modelProb))
                        liveEdge?.let {
                            StatChip("kenar", signedPct(it),
                                if (it >= 0.02) Ink.signal else Ink.caution)
                        }
                    }
                    if (liveEdge != null && liveEdge < 0.02) {
                        Text(
                            if (liveEdge < 0)
                                "Bu oranda beklenen getiri negatif. Kaydetmek serbest, " +
                                "ama oynamak için sebep yok."
                            else
                                "Kenar payı %2'nin altında — bu bant gürültüdür.",
                            style = MaterialTheme.typography.bodySmall, color = Ink.caution
                        )
                    }
                    stake?.let {
                        Text("Kasanın ${pct(it / bankroll.coerceAtLeast(1.0))}'i",
                            style = MaterialTheme.typography.bodySmall, color = Ink.faint)
                    }
                }
            }

            martingale?.let {
                Surface(shape = RoundedCornerShape(10.dp),
                    color = Ink.caution.copy(alpha = 0.12f),
                    modifier = Modifier.fillMaxWidth()) {
                    Text(it, Modifier.padding(14.dp),
                        style = MaterialTheme.typography.bodySmall, color = Ink.caution)
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(
                    onClick = { price?.let { onConfirm(it, 0.0, false) } },
                    enabled = price != null,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(10.dp)
                ) { Text("Oynamadım, kaydet", color = Ink.muted) }

                Button(
                    onClick = { if (price != null && stake != null) onConfirm(price, stake, true) },
                    enabled = price != null && stake != null && stake > 0,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Ink.signal,
                        contentColor = Ink.base)
                ) { Text("Oynadım") }
            }

            Text("Kapanış oranı maç başlayınca otomatik doldurulur; CLV o zaman hesaplanır.",
                style = MaterialTheme.typography.bodySmall, color = Ink.faint)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = Ink.signal, unfocusedBorderColor = Ink.line,
    focusedTextColor = Ink.text, unfocusedTextColor = Ink.text,
    focusedLabelColor = Ink.signal, unfocusedLabelColor = Ink.faint,
    cursorColor = Ink.signal
)

/** Sonuçlandırma: maç bitince kullanıcı sonucu işaretler. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettleBetDialog(
    matchLabel: String,
    selection: String,
    stake: Double,
    price: Double,
    onDismiss: () -> Unit,
    onSettle: (outcome: String) -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Ink.surface,
        title = { Text("Sonuç", color = Ink.text) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("$matchLabel · $selection", color = Ink.muted,
                    style = MaterialTheme.typography.bodyMedium)
                Text("Kazanırsa ${fmt(stake * (price - 1))} kâr, " +
                     "kaybederse ${fmt(stake)} zarar.",
                    color = Ink.faint, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically) {
                TextButton({ onSettle("PUSH") }) { Text("İade", color = Ink.faint) }
                TextButton({ onSettle("LOSE") }) { Text("Kaybetti", color = Ink.caution) }
                TextButton({ onSettle("WIN") }) { Text("Kazandı", color = Ink.signal) }
            }
        },
        dismissButton = { TextButton(onDismiss) { Text("Vazgeç", color = Ink.faint) } }
    )
}

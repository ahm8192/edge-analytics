package com.ahmet.edge.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ahmet.edge.ui.theme.Ink
import java.util.Locale

/**
 * Model olasılığı ile piyasa olasılığını YAN YANA gösterir.
 * Tek başına olasılık göstermek yanıltıcıdır — soru "ne kadar muhtemel" değil,
 * "piyasadan farklı mıyım".
 */
@Composable
fun ProbabilityRow(
    label: String,
    modelProb: Double,
    marketProb: Double?,
    price: Double?,
    fairPrice: Double,
    highlighted: Boolean = false
) {
    Row(
        Modifier.fillMaxWidth()
            .background(if (highlighted) Ink.signal.copy(alpha = 0.07f) else Color.Transparent,
                        RoundedCornerShape(6.dp))
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label, Modifier.width(52.dp), color = Ink.text,
            style = MaterialTheme.typography.titleMedium)

        Column(Modifier.weight(1f)) {
            ProbBar(modelProb, marketProb)
            Spacer(Modifier.height(4.dp))
            Text(
                buildString {
                    append("model ${pct(modelProb)}")
                    marketProb?.let { append("  ·  piyasa ${pct(it)}") }
                },
                style = MaterialTheme.typography.bodySmall, color = Ink.muted
            )
        }

        Column(horizontalAlignment = Alignment.End, modifier = Modifier.width(76.dp)) {
            Text(price?.let { fmt(it) } ?: "—", color = Ink.text,
                style = MaterialTheme.typography.titleMedium)
            Text("adil ${fmt(fairPrice)}", style = MaterialTheme.typography.bodySmall,
                color = if (price != null && price > fairPrice) Ink.signal else Ink.faint)
        }
    }
}

/** İki çubuk üst üste: dolu = model, ince çizgi = piyasa. Fark göz kararı okunur. */
@Composable
private fun ProbBar(model: Double, market: Double?) {
    Box(Modifier.fillMaxWidth().height(8.dp)
        .background(Ink.raised, RoundedCornerShape(4.dp))) {
        Box(Modifier.fillMaxWidth(model.toFloat().coerceIn(0f, 1f)).fillMaxHeight()
            .background(Ink.signal.copy(alpha = 0.85f), RoundedCornerShape(4.dp)))
        market?.let {
            Box(Modifier.fillMaxWidth(it.toFloat().coerceIn(0f, 1f)).fillMaxHeight()) {
                Box(Modifier.align(Alignment.CenterEnd).width(2.dp).fillMaxHeight()
                    .background(Ink.text))
            }
        }
    }
}

@Composable
fun StatChip(label: String, value: String, tint: Color = Ink.muted) {
    Column {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Ink.faint)
        Text(value, style = MaterialTheme.typography.titleMedium, color = tint,
            fontWeight = FontWeight.Medium)
    }
}

fun pct(v: Double): String = String.format(Locale.US, "%.1f%%", v * 100)
fun fmt(v: Double): String = String.format(Locale.US, "%.2f", v)
fun signedPct(v: Double): String = String.format(Locale.US, "%+.1f%%", v * 100)

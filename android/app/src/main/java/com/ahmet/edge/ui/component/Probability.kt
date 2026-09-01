package com.ahmet.edge.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ahmet.edge.ui.theme.DataStyle
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono

/**
 * Tek seçim satırı: model olasılığı vs piyasa olasılığı + oran / adil oran.
 * Soru "ne kadar muhtemel" değil, "piyasadan farklı mıyım".
 */
@Composable
fun ProbabilityRow(
    label: String,
    modelProb: Double,
    marketProb: Double?,
    price: Double?,
    fairPrice: Double,
    highlighted: Boolean = false,
) {
    val edge = if (marketProb != null && marketProb > 0) modelProb - marketProb else 0.0
    Row(
        Modifier
            .fillMaxWidth()
            .background(
                if (highlighted) Ink.accentDim else Color.Transparent,
                RoundedCornerShape(6.dp)
            )
            .then(
                if (highlighted) Modifier.border(1.dp, Ink.accent.copy(alpha = 0.3f),
                    RoundedCornerShape(6.dp)) else Modifier
            )
            .padding(horizontal = 12.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(label, Modifier.width(44.dp), color = Ink.text,
            style = MaterialTheme.typography.titleMedium)

        Column(Modifier.weight(1f)) {
            SingleBar(modelProb, marketProb)
            Spacer(Modifier.height(5.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("MODEL ${pct(modelProb)}", style = LabelMono.copy(fontSize = 10.sp),
                    color = Ink.muted)
                marketProb?.let {
                    Text("PİYASA ${pct(it)}", style = LabelMono.copy(fontSize = 10.sp),
                        color = Ink.faint)
                }
            }
        }

        Column(horizontalAlignment = Alignment.End, modifier = Modifier.width(72.dp)) {
            Text(price?.let { fmt(it) } ?: "—", color = Ink.text,
                style = DataStyle.copy(fontSize = 15.sp))
            Text("adil ${fmt(fairPrice)}", style = LabelMono.copy(fontSize = 10.sp),
                color = if (edge > 0.015) Ink.signal else Ink.faint)
        }
    }
}

/** Dolu = model, dikey imleç = piyasa. Fark göz kararı okunur. */
@Composable
private fun SingleBar(model: Double, market: Double?) {
    Box(
        Modifier.fillMaxWidth().height(6.dp)
            .background(Ink.raised, RoundedCornerShape(2.dp))
    ) {
        Box(
            Modifier.fillMaxWidth(model.toFloat().coerceIn(0f, 1f)).fillMaxHeight()
                .background(Ink.accent, RoundedCornerShape(2.dp))
        )
        market?.let {
            Box(Modifier.fillMaxWidth(it.toFloat().coerceIn(0f, 1f)).fillMaxHeight()) {
                Box(
                    Modifier.align(Alignment.CenterEnd).width(2.dp).fillMaxHeight()
                        .background(Ink.text)
                )
            }
        }
    }
}

@Composable
fun StatChip(label: String, value: String, tint: Color = Ink.text) {
    StatCell(label = label, value = value, tint = tint)
}

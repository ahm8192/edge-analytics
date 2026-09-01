package com.ahmet.edge.ui.component

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp
import com.ahmet.edge.domain.model.OddsPoint
import com.ahmet.edge.ui.theme.Ink
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Açılıştan kapanışa oran eğrisi (madde 7, 83).
 *
 * Neden değerli: oranın YÖNÜ, seviyesinden daha çok bilgi taşır.
 * Oran düşüyorsa bilgili para o tarafa akıyor demektir. Senin aldığın
 * fiyatın nerede durduğunu görmeden kenar payı soyut kalır.
 */
@Composable
fun OddsMovementChart(
    points: List<OddsPoint>,
    fairPrice: Double?,
    takenPrice: Double? = null,
    modifier: Modifier = Modifier
) {
    if (points.size < 2) {
        Text("Hareket verisi henüz yeterli değil.",
            style = MaterialTheme.typography.bodySmall, color = Ink.faint)
        return
    }

    val prices = points.map { it.price }
    val candidates = listOfNotNull(fairPrice, takenPrice) + prices
    val lo = candidates.min() * 0.98
    val hi = candidates.max() * 1.02
    val span = (hi - lo).coerceAtLeast(1e-6)

    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().height(140.dp)) {
            fun xOf(i: Int) = size.width * i / (points.size - 1).toFloat()
            fun yOf(p: Double) = size.height * (1f - ((p - lo) / span).toFloat())

            // Adil oran referans çizgisi: eğri bunun ÜSTÜNDEYSE değer var
            fairPrice?.let { fp ->
                drawLine(
                    color = Ink.signal.copy(alpha = 0.55f),
                    start = Offset(0f, yOf(fp)),
                    end = Offset(size.width, yOf(fp)),
                    strokeWidth = 1.5f,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f))
                )
            }

            val path = Path().apply {
                moveTo(xOf(0), yOf(prices[0]))
                for (i in 1 until points.size) lineTo(xOf(i), yOf(prices[i]))
            }
            drawPath(path, Ink.text, style = Stroke(width = 2.5f))

            // Aldığın fiyat işaretlenir — sonradan CLV bu noktadan okunur
            takenPrice?.let { tp ->
                drawCircle(Ink.brass, radius = 5f,
                    center = Offset(xOf(points.size / 2), yOf(tp)))
            }

            drawCircle(Ink.signal, radius = 4f,
                center = Offset(xOf(points.size - 1), yOf(prices.last())))
        }

        Spacer(Modifier.height(8.dp))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            AxisLabel(points.first(), "açılış")
            AxisLabel(points.last(), "son")
        }

        val drift = prices.last() / prices.first() - 1.0
        Spacer(Modifier.height(6.dp))
        Text(
            when {
                drift < -0.03 -> "Oran düşüyor (${signedPct(drift)}) — para bu tarafa akıyor."
                drift > 0.03 -> "Oran yükseliyor (${signedPct(drift)}) — piyasa bu taraftan uzaklaşıyor."
                else -> "Oran sabit (${signedPct(drift)})."
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (drift < -0.03) Ink.signal else Ink.muted
        )
    }
}

@Composable
private fun AxisLabel(p: OddsPoint, tag: String) {
    Column {
        Text(fmt(p.price), style = MaterialTheme.typography.bodyMedium, color = Ink.text)
        Text("$tag · ${chartFmt.format(p.at.atZone(ZoneId.systemDefault()))}",
            style = MaterialTheme.typography.bodySmall, color = Ink.faint)
    }
}

private val chartFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("d MMM HH:mm")

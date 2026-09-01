package com.ahmet.edge.ui.component

import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import coil.request.ImageRequest
import androidx.compose.ui.platform.LocalContext
import com.ahmet.edge.ui.theme.DataStyle
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono
import com.ahmet.edge.ui.theme.PlexMono
import java.util.Locale

// ------------------------------------------------------------------ formatlar
fun pct(v: Double): String = String.format(Locale.US, "%.1f%%", v * 100)
fun pct0(v: Double): String = String.format(Locale.US, "%.0f%%", v * 100)
fun fmt(v: Double): String = String.format(Locale.US, "%.2f", v)
fun signedPct(v: Double): String = String.format(Locale.US, "%+.1f%%", v * 100)

// ------------------------------------------------------------------ yüzey
val CardShape = RoundedCornerShape(7.dp)
val ChipShape = RoundedCornerShape(4.dp)

@Composable
fun Panel(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    padding: PaddingValues = PaddingValues(14.dp),
    content: @Composable ColumnScope.() -> Unit,
) {
    val base = modifier
        .fillMaxWidth()
        .clip(CardShape)
        .background(Ink.surface)
        .border(1.dp, Ink.line, CardShape)
        .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
        .padding(padding)
    Column(base, content = content)
}

/** Büyük harf mono bölüm etiketi + isteğe bağlı sağ aksiyon. */
@Composable
fun SectionLabel(
    text: String,
    modifier: Modifier = Modifier,
    trailing: @Composable (RowScope.() -> Unit)? = null,
) {
    Row(
        modifier.fillMaxWidth().padding(top = 4.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(text.uppercase(Locale.US), style = LabelMono, color = Ink.faint)
        Spacer(Modifier.weight(1f))
        trailing?.invoke(this)
    }
}

@Composable
fun Hairline(modifier: Modifier = Modifier) =
    Box(modifier.fillMaxWidth().height(1.dp).background(Ink.line))

// ------------------------------------------------------------------ rozetler
/** Edge etiketi: +%3.2 yeşil, −%1.1 kırmızı, 0 civarı nötr. */
@Composable
fun EdgeTag(edgePct: Double, modifier: Modifier = Modifier) {
    val c = when {
        edgePct >= 0.015 -> Ink.signal
        edgePct <= -0.015 -> Ink.caution
        else -> Ink.muted
    }
    Box(
        modifier
            .clip(ChipShape)
            .background(c.copy(alpha = 0.14f))
            .border(1.dp, c.copy(alpha = 0.35f), ChipShape)
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(signedPct(edgePct), style = DataStyle.copy(fontSize = 12.sp), color = c)
    }
}

/** Güven: 3 kademe dolu çubuk. */
@Composable
fun ConfidenceMeter(confidence: Double, modifier: Modifier = Modifier) {
    val filled = when {
        confidence >= 0.66 -> 3
        confidence >= 0.4 -> 2
        confidence > 0.0 -> 1
        else -> 0
    }
    val c = if (filled >= 3) Ink.text else if (filled == 2) Ink.muted else Ink.caution
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(2.dp),
        verticalAlignment = Alignment.Bottom) {
        repeat(3) { i ->
            Box(
                Modifier
                    .width(3.dp)
                    .height((6 + i * 4).dp)
                    .background(if (i < filled) c else Ink.lineStrong,
                        RoundedCornerShape(1.dp))
            )
        }
    }
}

@Composable
fun Tag(text: String, color: Color = Ink.muted, modifier: Modifier = Modifier) {
    Box(
        modifier.clip(ChipShape).background(color.copy(alpha = 0.12f))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) { Text(text.uppercase(Locale.US), style = LabelMono.copy(fontSize = 10.sp), color = color) }
}

// ------------------------------------------------------------------ olasılık çubuğu
/** 1X2 segmentli çubuk. 2px boşluklu, uçları hafif yuvarlak. */
@Composable
fun ProbBar3(
    home: Double, draw: Double, away: Double,
    modifier: Modifier = Modifier,
    height: Dp = 6.dp,
) {
    val h = home.toFloat().coerceAtLeast(0f)
    val d = draw.toFloat().coerceAtLeast(0f)
    val a = away.toFloat().coerceAtLeast(0f)
    Row(
        modifier.fillMaxWidth().height(height).clip(RoundedCornerShape(2.dp)),
        horizontalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        if (h > 0) Box(Modifier.weight(h).fillMaxHeight().background(Ink.home))
        if (d > 0) Box(Modifier.weight(d).fillMaxHeight().background(Ink.draw))
        if (a > 0) Box(Modifier.weight(a).fillMaxHeight().background(Ink.away))
    }
}

@Composable
fun ProbLegendRow(home: Double, draw: Double, away: Double, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        LegendItem("1", home, Ink.home)
        LegendItem("X", draw, Ink.draw)
        LegendItem("2", away, Ink.away)
    }
}

@Composable
private fun LegendItem(k: String, v: Double, c: Color) {
    Row(verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        Box(Modifier.size(6.dp).background(c, RoundedCornerShape(1.dp)))
        Text(k, style = LabelMono, color = Ink.faint)
        Text(pct0(v), style = DataStyle.copy(fontSize = 13.sp), color = Ink.text)
    }
}

// ------------------------------------------------------------------ arma
@Composable
fun TeamCrest(url: String?, name: String, size: Dp = 30.dp) {
    var failed by remember(url) { mutableStateOf(false) }
    if (url.isNullOrBlank() || failed) {
        val shape = RoundedCornerShape(6.dp)
        Box(
            Modifier.size(size).clip(shape).background(Ink.raised)
                .border(1.dp, Ink.line, shape),
            contentAlignment = Alignment.Center
        ) {
            Text(
                name.trim().take(2).uppercase(Locale.US),
                style = LabelMono.copy(fontSize = (size.value * 0.34f).sp), color = Ink.muted
            )
        }
    } else {
        AsyncImage(
            model = ImageRequest.Builder(LocalContext.current).data(url)
                .crossfade(true).build(),
            contentDescription = name,
            onError = { failed = true },
            modifier = Modifier.size(size)
        )
    }
}

// ------------------------------------------------------------------ butonlar
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp))
            .background(Ink.accent).clickable(onClick = onClick)
            .padding(vertical = 13.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(text, color = Ink.base, style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun GhostButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier.fillMaxWidth().clip(RoundedCornerShape(6.dp))
            .border(1.dp, Ink.lineStrong, RoundedCornerShape(6.dp))
            .clickable(onClick = onClick).padding(vertical = 13.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(text, color = Ink.text, style = MaterialTheme.typography.labelLarge)
    }
}

// ------------------------------------------------------------------ durumlar
@Composable
fun Skeleton(modifier: Modifier = Modifier, shape: RoundedCornerShape = CardShape) {
    val t = rememberInfiniteTransition(label = "sk")
    val phase by t.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1200, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "phase"
    )
    val a = androidx.compose.ui.util.lerp(-320f, 640f, phase)
    val brush = Brush.linearGradient(
        colors = listOf(Ink.surface, Ink.raised, Ink.surface),
        start = androidx.compose.ui.geometry.Offset(a, 0f),
        end = androidx.compose.ui.geometry.Offset(a + 320f, 0f)
    )
    Box(modifier.clip(shape).background(brush).border(1.dp, Ink.line, shape))
}

@Composable
fun EmptyState(
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    action: (@Composable () -> Unit)? = null,
) {
    Column(
        modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 56.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(40.dp).clip(RoundedCornerShape(8.dp))
                .border(1.dp, Ink.lineStrong, RoundedCornerShape(8.dp)),
            contentAlignment = Alignment.Center
        ) { Text("λ", style = DataStyle.copy(fontSize = 20.sp), color = Ink.faint) }
        Spacer(Modifier.height(14.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, color = Ink.text)
        Spacer(Modifier.height(4.dp))
        Text(body, style = MaterialTheme.typography.bodySmall, color = Ink.muted,
            textAlign = TextAlign.Center)
        if (action != null) { Spacer(Modifier.height(18.dp)); action() }
    }
}

// ------------------------------------------------------------------ hücre
@Composable
fun StatCell(label: String, value: String, tint: Color = Ink.text, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label.uppercase(Locale.US), style = LabelMono.copy(fontSize = 10.sp), color = Ink.faint)
        Spacer(Modifier.height(3.dp))
        Text(value, style = DataStyle.copy(fontSize = 15.sp), color = tint)
    }
}

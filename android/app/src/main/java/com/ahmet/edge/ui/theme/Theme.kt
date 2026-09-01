package com.ahmet.edge.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/**
 * Tasarım yönü: ölçüm aleti, kumarhane değil.
 * Kırmızı/yeşil ikilisinden kaçınıldı — o palet bahis uygulamalarının klişesi
 * ve duygusal karar verdirir. Değer tek bir turkuaz sinyalle, risk kehribar
 * tonuyla anlatılır. Abonelik işareti eskimiş pirinç: kazanılmış, süs değil.
 */
object Ink {
    val base = Color(0xFF0B0F14)
    val surface = Color(0xFF141A21)
    val raised = Color(0xFF1D252E)
    val line = Color(0xFF2A343F)

    val text = Color(0xFFE4EAF0)
    val muted = Color(0xFF7E8C9A)
    val faint = Color(0xFF4C5A68)

    val signal = Color(0xFF35C3A6)     // değer var
    val caution = Color(0xFFE0803C)    // dikkat / risk
    val brass = Color(0xFFC9A227)      // abonelik
}

private val Dark = darkColorScheme(
    primary = Ink.signal,
    onPrimary = Ink.base,
    secondary = Ink.brass,
    background = Ink.base,
    onBackground = Ink.text,
    surface = Ink.surface,
    onSurface = Ink.text,
    surfaceVariant = Ink.raised,
    onSurfaceVariant = Ink.muted,
    outline = Ink.line,
    error = Ink.caution
)

/**
 * Sayı hizalaması bu uygulamada kritik: olasılık sütunları alt alta
 * okunacak. tabular figürler (tnum) olmadan virgüller kayar.
 */
private val tabular = "tnum"

val Numeric = TextStyle(
    fontFeatureSettings = tabular,
    fontWeight = FontWeight.Medium,
    letterSpacing = 0.sp
)

private val EdgeType = Typography(
    displaySmall = TextStyle(fontSize = 32.sp, fontWeight = FontWeight.SemiBold,
        letterSpacing = (-0.5).sp, fontFeatureSettings = tabular),
    headlineSmall = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Medium),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontSize = 13.sp, lineHeight = 19.sp),
    labelMedium = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.Medium,
        fontFeatureSettings = tabular)
)

@Composable
fun EdgeTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = Dark, typography = EdgeType, content = content)

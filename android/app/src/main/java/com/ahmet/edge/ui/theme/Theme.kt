package com.ahmet.edge.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.ahmet.edge.R

/**
 * "Lambda" — kuantitatif terminal. Neredeyse siyah, katmanlı yüzeyler, gölge yok,
 * saç teli çizgiler. Tek ölçülü vurgu: kehribar. Yeşil/kırmızı sadece P&L / +EV.
 * Bütün sayılar monospace + tabular. Sıkı tipografi — abartısız, yoğun.
 */
object Ink {
    val base = Color(0xFF08090B)
    val surface = Color(0xFF101216)
    val raised = Color(0xFF171A1F)
    val line = Color(0xFF20242B)
    val lineStrong = Color(0xFF2C313A)

    val text = Color(0xFFEAECEF)
    val muted = Color(0xFF888F98)
    val faint = Color(0xFF565D66)

    val accent = Color(0xFFF5A623)
    val accentDim = Color(0x1FF5A623)

    val signal = Color(0xFF34D399)   // +EV / kazanç
    val caution = Color(0xFFF5555D)  // −EV / kayıp
    val brass = Color(0xFFF5A623)    // geri uyumluluk

    val home = Color(0xFF4C8DFF)
    val draw = Color(0xFF636B78)
    val away = Color(0xFFF2A73B)
}

val PlexSans = FontFamily(
    Font(R.font.plex_sans_regular, FontWeight.Normal),
    Font(R.font.plex_sans_medium, FontWeight.Medium),
    Font(R.font.plex_sans_semibold, FontWeight.SemiBold),
)
val PlexMono = FontFamily(
    Font(R.font.plex_mono_regular, FontWeight.Normal),
    Font(R.font.plex_mono_medium, FontWeight.Medium),
    Font(R.font.plex_mono_semibold, FontWeight.SemiBold),
)

private const val tnum = "tnum"

/** Bölüm başlığı: mono, seyrek, büyük harf, kısık. */
val LabelMono = TextStyle(
    fontFamily = PlexMono, fontWeight = FontWeight.Medium,
    fontSize = 10.sp, letterSpacing = 1.1.sp
)

/** Rakam bloğu — olasılık, oran, tutar. Her zaman tabular. */
val DataStyle = TextStyle(
    fontFamily = PlexMono, fontWeight = FontWeight.Medium,
    fontFeatureSettings = tnum, letterSpacing = 0.sp, fontSize = 13.sp
)

private val Dark = darkColorScheme(
    primary = Ink.accent, onPrimary = Ink.base,
    secondary = Ink.accent,
    background = Ink.base, onBackground = Ink.text,
    surface = Ink.surface, onSurface = Ink.text,
    surfaceVariant = Ink.raised, onSurfaceVariant = Ink.muted,
    outline = Ink.line, error = Ink.caution,
)

private val EdgeType = Typography(
    displaySmall = TextStyle(fontFamily = PlexMono, fontWeight = FontWeight.SemiBold,
        fontSize = 26.sp, letterSpacing = (-0.4).sp, fontFeatureSettings = tnum),
    headlineSmall = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold,
        fontSize = 18.sp, letterSpacing = (-0.2).sp),
    titleLarge = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold,
        fontSize = 15.sp),
    titleMedium = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Medium,
        fontSize = 13.5.sp),
    bodyLarge = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Normal,
        fontSize = 14.sp, lineHeight = 20.sp),
    bodyMedium = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Normal,
        fontSize = 12.5.sp, lineHeight = 18.sp),
    bodySmall = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Normal,
        fontSize = 11.5.sp, lineHeight = 16.sp, color = Ink.muted),
    labelLarge = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp, letterSpacing = 0.2.sp),
    labelMedium = LabelMono,
    labelSmall = TextStyle(fontFamily = PlexMono, fontWeight = FontWeight.Medium,
        fontSize = 10.sp, fontFeatureSettings = tnum),
)

@Composable
fun EdgeTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = Dark, typography = EdgeType, content = content)

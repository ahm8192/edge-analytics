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
 * "Lambda" — kuantitatif terminal.
 * Ölçüm aleti, kumarhane değil. Neredeyse siyah, katmanlı yüzeyler,
 * gölge yok — saç teli çizgiler. Tek ölçülü vurgu: kehribar.
 * Yeşil/kırmızı YALNIZCA kâr-zarar ve +EV/−EV için; başka yerde kullanılmaz.
 * Bütün sayılar monospace ve tabular — sütunlar alt alta kayarsa okunmaz.
 */
object Ink {
    val base = Color(0xFF08090B)      // uygulama zemini
    val surface = Color(0xFF101216)   // kart
    val raised = Color(0xFF171A1F)    // yükseltilmiş / girdi / basılı
    val line = Color(0xFF22262D)      // saç teli ayraç
    val lineStrong = Color(0xFF2E333C)

    val text = Color(0xFFEAECEF)
    val muted = Color(0xFF8B929B)
    val faint = Color(0xFF565D66)

    val accent = Color(0xFFF5A623)    // marka / etkileşim / odak / PRO
    val accentDim = Color(0x1FF5A623)

    // Sadece kâr-zarar ve değer işareti:
    val signal = Color(0xFF34D399)    // +EV / kazanç
    val caution = Color(0xFFF5555D)   // −EV / kayıp
    val brass = Color(0xFFF5A623)     // (geri uyumluluk — accent ile aynı)

    // 1X2 olasılık çubuğu — kategorik üçlü (CVD ayrımı: mavi/eğik-gri/kehribar)
    val home = Color(0xFF4C8DFF)
    val draw = Color(0xFF6B7480)
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

private val tnum = "tnum"

/** Bölüm başlığı: mono, seyrek, büyük harf, kısık. */
val LabelMono = TextStyle(
    fontFamily = PlexMono, fontWeight = FontWeight.Medium,
    fontSize = 11.sp, letterSpacing = 1.6.sp
)

/** Rakam bloğu — olasılık, oran, tutar. Her zaman tabular. */
val DataStyle = TextStyle(
    fontFamily = PlexMono, fontWeight = FontWeight.Medium,
    fontFeatureSettings = tnum, letterSpacing = 0.sp, fontSize = 14.sp
)

private val Dark = darkColorScheme(
    primary = Ink.accent,
    onPrimary = Ink.base,
    secondary = Ink.accent,
    background = Ink.base,
    onBackground = Ink.text,
    surface = Ink.surface,
    onSurface = Ink.text,
    surfaceVariant = Ink.raised,
    onSurfaceVariant = Ink.muted,
    outline = Ink.line,
    error = Ink.caution,
)

private val EdgeType = Typography(
    // Hero sayı (maç detayı olasılığı, kasa bakiyesi)
    displaySmall = TextStyle(fontFamily = PlexMono, fontWeight = FontWeight.SemiBold,
        fontSize = 34.sp, letterSpacing = (-0.5).sp, fontFeatureSettings = tnum),
    headlineSmall = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold,
        fontSize = 21.sp, letterSpacing = (-0.2).sp),
    titleLarge = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp),
    titleMedium = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Medium,
        fontSize = 15.sp),
    bodyLarge = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Normal,
        fontSize = 15.sp, lineHeight = 22.sp),
    bodyMedium = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Normal,
        fontSize = 13.5.sp, lineHeight = 20.sp),
    bodySmall = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.Normal,
        fontSize = 12.sp, lineHeight = 17.sp, color = Ink.muted),
    labelLarge = TextStyle(fontFamily = PlexSans, fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp, letterSpacing = 0.2.sp),
    labelMedium = LabelMono,
    labelSmall = TextStyle(fontFamily = PlexMono, fontWeight = FontWeight.Medium,
        fontSize = 11.sp, fontFeatureSettings = tnum),
)

@Composable
fun EdgeTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = Dark, typography = EdgeType, content = content)

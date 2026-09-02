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
 * "Lambda — Matchday". Yayın skorbordu dili: stadyum-gecesi lacivert zemin,
 * takım rengi her satırı sürer. Sarı = marka / model seçimi, yeşil = değer / P&L,
 * kırmızı = canlı / kayıp. Başlıklar sıkıştırılmış (Barlow Condensed), gövde Barlow.
 *
 * Not: eski isimler (Ink.*, PlexSans, PlexMono) korunuyor ki tüm çağrı yerleri
 * derlensin — sadece değerler değişti.
 */
object Ink {
    val base = Color(0xFF0A101C)        // pitch
    val surface = Color(0xFF111A2B)
    val raised = Color(0xFF16202F)
    val line = Color(0xFF212C3E)
    val lineStrong = Color(0xFF33405A)

    val text = Color(0xFFF3F6FB)
    val muted = Color(0xFF93A1B6)
    val faint = Color(0xFF59667C)

    val accent = Color(0xFFFFC61A)      // yayın sarısı — marka / model seçimi
    val accentDim = Color(0x1FFFC61A)

    val signal = Color(0xFF12D18E)      // +EV / kazanç
    val caution = Color(0xFFFF2E4D)     // canlı / −EV / kayıp
    val brass = Color(0xFFFFC61A)       // geri uyumluluk

    val live = Color(0xFFFF2E4D)

    val home = Color(0xFF4C8DFF)
    val draw = Color(0xFF565E6B)
    val away = Color(0xFFF2A73B)
}

val Barlow = FontFamily(
    Font(R.font.barlow_regular, FontWeight.Normal),
    Font(R.font.barlow_medium, FontWeight.Medium),
    Font(R.font.barlow_semibold, FontWeight.SemiBold),
    Font(R.font.barlow_bold, FontWeight.Bold),
)
val BarlowCondensed = FontFamily(
    Font(R.font.barlow_condensed_medium, FontWeight.Normal),
    Font(R.font.barlow_condensed_medium, FontWeight.Medium),
    Font(R.font.barlow_condensed_semibold, FontWeight.SemiBold),
    Font(R.font.barlow_condensed_bold, FontWeight.Bold),
)

/** Geri uyumluluk: eski kod bu isimleri kullanıyor. */
val PlexSans = Barlow
val PlexMono = BarlowCondensed

private const val tnum = "tnum"

/** Bölüm / etiket başlığı — sıkıştırılmış, seyrek, büyük harf (call-site'ta uppercase). */
val LabelMono = TextStyle(
    fontFamily = BarlowCondensed, fontWeight = FontWeight.Medium,
    fontSize = 11.sp, letterSpacing = 0.9.sp
)

/** Rakam bloğu — olasılık, oran, skor, tutar. Tabular. */
val DataStyle = TextStyle(
    fontFamily = BarlowCondensed, fontWeight = FontWeight.SemiBold,
    fontFeatureSettings = tnum, letterSpacing = 0.3.sp, fontSize = 14.sp
)

private val Dark = darkColorScheme(
    primary = Ink.accent, onPrimary = Color(0xFF1A1400),
    secondary = Ink.accent,
    background = Ink.base, onBackground = Ink.text,
    surface = Ink.surface, onSurface = Ink.text,
    surfaceVariant = Ink.raised, onSurfaceVariant = Ink.muted,
    outline = Ink.line, error = Ink.caution,
)

private val EdgeType = Typography(
    displaySmall = TextStyle(fontFamily = BarlowCondensed, fontWeight = FontWeight.Bold,
        fontSize = 32.sp, letterSpacing = 0.4.sp, fontFeatureSettings = tnum),
    headlineSmall = TextStyle(fontFamily = BarlowCondensed, fontWeight = FontWeight.Bold,
        fontSize = 22.sp, letterSpacing = 0.4.sp),
    titleLarge = TextStyle(fontFamily = BarlowCondensed, fontWeight = FontWeight.SemiBold,
        fontSize = 17.sp, letterSpacing = 0.3.sp),
    titleMedium = TextStyle(fontFamily = BarlowCondensed, fontWeight = FontWeight.SemiBold,
        fontSize = 15.sp, letterSpacing = 0.2.sp),
    bodyLarge = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal,
        fontSize = 14.sp, lineHeight = 20.sp),
    bodyMedium = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal,
        fontSize = 12.5.sp, lineHeight = 18.sp),
    bodySmall = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.Normal,
        fontSize = 11.5.sp, lineHeight = 16.sp, color = Ink.muted),
    labelLarge = TextStyle(fontFamily = Barlow, fontWeight = FontWeight.SemiBold,
        fontSize = 13.sp, letterSpacing = 0.3.sp),
    labelMedium = LabelMono,
    labelSmall = TextStyle(fontFamily = BarlowCondensed, fontWeight = FontWeight.Medium,
        fontSize = 10.sp, letterSpacing = 0.5.sp, fontFeatureSettings = tnum),
)

@Composable
fun EdgeTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = Dark, typography = EdgeType, content = content)

package com.ahmet.edge.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
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

// Barlow'un dahili satır metrikleri gevşek — font-padding kapat, sıkı satır yüksekliği ver.
private val Tight = PlatformTextStyle(includeFontPadding = false)
private val LHS = LineHeightStyle(
    alignment = LineHeightStyle.Alignment.Center,
    trim = LineHeightStyle.Trim.Both
)

/** Bölüm / etiket başlığı — sıkıştırılmış, seyrek, büyük harf (call-site'ta uppercase). */
val LabelMono = TextStyle(
    fontFamily = BarlowCondensed, fontWeight = FontWeight.Medium,
    fontSize = 11.sp, lineHeight = 12.sp, letterSpacing = 0.9.sp,
    platformStyle = Tight, lineHeightStyle = LHS
)

/** Rakam bloğu — olasılık, oran, skor, tutar. Tabular. */
val DataStyle = TextStyle(
    fontFamily = BarlowCondensed, fontWeight = FontWeight.SemiBold,
    fontFeatureSettings = tnum, letterSpacing = 0.3.sp, fontSize = 14.sp, lineHeight = 15.sp,
    platformStyle = Tight, lineHeightStyle = LHS
)

private val Dark = darkColorScheme(
    primary = Ink.accent, onPrimary = Color(0xFF1A1400),
    secondary = Ink.accent,
    background = Ink.base, onBackground = Ink.text,
    surface = Ink.surface, onSurface = Ink.text,
    surfaceVariant = Ink.raised, onSurfaceVariant = Ink.muted,
    outline = Ink.line, error = Ink.caution,
)

private fun cond(size: Int, weight: FontWeight, ls: Double = 0.3, lh: Int = 0) = TextStyle(
    fontFamily = BarlowCondensed, fontWeight = weight, fontSize = size.sp,
    lineHeight = (if (lh > 0) lh else size + 2).sp, letterSpacing = ls.sp,
    fontFeatureSettings = tnum, platformStyle = Tight, lineHeightStyle = LHS,
)

private fun sans(size: Double, weight: FontWeight, lh: Double) = TextStyle(
    fontFamily = Barlow, fontWeight = weight, fontSize = size.sp, lineHeight = lh.sp,
    platformStyle = Tight, lineHeightStyle = LHS,
)

private val EdgeType = Typography(
    displaySmall = cond(32, FontWeight.Bold, 0.4),
    headlineSmall = cond(22, FontWeight.Bold, 0.4),
    titleLarge = cond(17, FontWeight.SemiBold, 0.3),
    titleMedium = cond(15, FontWeight.SemiBold, 0.2),
    bodyLarge = sans(14.0, FontWeight.Normal, 19.0),
    bodyMedium = sans(12.5, FontWeight.Normal, 17.0),
    bodySmall = sans(11.5, FontWeight.Normal, 15.0).copy(color = Ink.muted),
    labelLarge = sans(13.0, FontWeight.SemiBold, 15.0).copy(letterSpacing = 0.3.sp),
    labelMedium = LabelMono,
    labelSmall = cond(10, FontWeight.Medium, 0.5),
)

@Composable
fun EdgeTheme(content: @Composable () -> Unit) =
    MaterialTheme(colorScheme = Dark, typography = EdgeType, content = content)

package com.ahmet.edge.ui.theme

import androidx.compose.ui.graphics.Color
import java.util.Locale
import kotlin.math.abs

/**
 * Takım kimliği — yayın dili: kulüp rengi + 3 harfli kod.
 * Eşleşmeyen takımlar isimden türeyen sabit bir renk alır (asla gri kalmaz).
 */
object TeamStyle {

    private val ROOT: Locale = Locale.ROOT

    private fun norm(s: String): String =
        s.lowercase(ROOT)
            .replace(Regex("[àáâãäå]"), "a").replace(Regex("[èéêë]"), "e")
            .replace(Regex("[ìíîï]"), "i").replace(Regex("[òóôõö]"), "o")
            .replace(Regex("[ùúûü]"), "u").replace(Regex("ç"), "c").replace(Regex("ñ"), "n")
            .replace(Regex("\\b(fc|afc|cf|sc|ac|cd|sv|if|bk|club|the|1899|1900|1904|1907|09)\\b"), " ")
            .replace(Regex("[^a-z0-9 ]"), " ")
            .trim().replace(Regex("\\s+"), " ")

    /** "Queens Park Rangers" -> QPR · "Cardiff City" -> CAR · "Wrexham" -> WRE */
    fun code(name: String): String {
        val w = norm(name).uppercase(ROOT).split(" ").filter { it.isNotBlank() }
        return when {
            w.isEmpty() -> name.filter { it.isLetterOrDigit() }.take(3).uppercase(ROOT).ifBlank { "?" }
            w.size >= 3 -> w.joinToString("") { it.take(1) }.take(4)
            else -> w[0].take(3)
        }
    }

    /** İki takım aynı kodu üretiyorsa ayrıştır. */
    fun codes(home: String, away: String): Pair<String, String> {
        val h = code(home); val a = code(away)
        if (!h.equals(a, ignoreCase = true)) return h to a
        fun alt(n: String): String {
            val w = norm(n).uppercase(ROOT).split(" ").filter { it.isNotBlank() }
            return if (w.size >= 2) w[0].take(1) + w[1].take(2) else w.getOrElse(0) { n }.take(4)
        }
        return alt(home) to alt(away)
    }

    private val MAP: Map<String, Long> = buildMap {
        // Premier League / Championship / EFL
        put("arsenal", 0xFFEF0107); put("chelsea", 0xFF034694); put("liverpool", 0xFFC8102E)
        put("manchester city", 0xFF6CABDD); put("manchester united", 0xFFDA291C)
        put("tottenham", 0xFF132257); put("tottenham hotspur", 0xFF132257)
        put("newcastle", 0xFF241F20); put("newcastle united", 0xFF241F20)
        put("aston villa", 0xFF95BFE5); put("west ham", 0xFF7A263A); put("west ham united", 0xFF7A263A)
        put("brighton", 0xFF0057B8); put("brighton hove albion", 0xFF0057B8)
        put("wolves", 0xFFFDB913); put("wolverhampton wanderers", 0xFFFDB913)
        put("everton", 0xFF003399); put("fulham", 0xFF1B1B1B); put("crystal palace", 0xFF1B458F)
        put("brentford", 0xFFE30613); put("nottingham forest", 0xFFDD0000); put("bournemouth", 0xFFDA291C)
        put("leeds united", 0xFF1D428A); put("leicester city", 0xFF003090); put("southampton", 0xFFD71920)
        put("ipswich town", 0xFF3A64A3)
        put("millwall", 0xFF1B3A8C); put("wrexham", 0xFFC8102E)
        put("queens park rangers", 0xFF1D5BA4); put("qpr", 0xFF1D5BA4)
        put("cardiff city", 0xFF0070B5); put("cardiff", 0xFF0070B5)
        put("west bromwich albion", 0xFF122F67); put("west brom", 0xFF122F67)
        put("charlton athletic", 0xFFC40E23); put("charlton", 0xFFC40E23)
        put("burnley", 0xFF6C1D45); put("middlesbrough", 0xFFE21C38)
        put("norwich city", 0xFFFFF200); put("watford", 0xFFFBEE23); put("hull city", 0xFFF5A12D)
        put("sheffield united", 0xFFEE2737); put("sheffield wednesday", 0xFF1F3A8A)
        put("coventry city", 0xFF6CCFF6); put("sunderland", 0xFFEB172B); put("preston north end", 0xFFB2B2B2)
        put("bristol city", 0xFFE21C38); put("stoke city", 0xFFE03A3E); put("swansea city", 0xFF121212)
        put("blackburn rovers", 0xFF009EE0); put("plymouth argyle", 0xFF007B5F); put("oxford united", 0xFFFFD100)
        put("portsmouth", 0xFF001489); put("derby county", 0xFF1B1B1B); put("luton town", 0xFFFF5000)
        // Bundesliga
        put("bayern munich", 0xFFDC052D); put("bayern", 0xFFDC052D)
        put("borussia dortmund", 0xFFFDE100); put("dortmund", 0xFFFDE100)
        put("rb leipzig", 0xFF001F47); put("leipzig", 0xFF001F47)
        put("bayer leverkusen", 0xFFE32221); put("leverkusen", 0xFFE32221)
        put("borussia monchengladbach", 0xFF000000); put("monchengladbach", 0xFF000000)
        put("eintracht frankfurt", 0xFF1C1C1C); put("frankfurt", 0xFF1C1C1C)
        put("vfb stuttgart", 0xFFE32219); put("stuttgart", 0xFFE32219)
        put("werder bremen", 0xFF1D9053); put("wolfsburg", 0xFF65B32E); put("freiburg", 0xFF5B5B5B)
        put("hoffenheim", 0xFF1C63B7); put("mainz", 0xFFC3141E); put("augsburg", 0xFFBA3733)
        put("union berlin", 0xFFEB1923); put("schalke", 0xFF004B9E); put("schalke 04", 0xFF004B9E)
        put("hamburger sv", 0xFF0A3A82); put("hamburg", 0xFF0A3A82); put("koln", 0xFFED1C24)
        // La Liga
        put("real madrid", 0xFFFEBE10); put("barcelona", 0xFFA50044); put("atletico madrid", 0xFFCB3524)
        put("atletico", 0xFFCB3524); put("sevilla", 0xFFD8241F); put("real betis", 0xFF0BB363)
        put("betis", 0xFF0BB363); put("real sociedad", 0xFF0067B1); put("villarreal", 0xFFFFE667)
        put("athletic club", 0xFFEE2523); put("athletic bilbao", 0xFFEE2523); put("valencia", 0xFFF3B300)
        put("getafe", 0xFF005999); put("girona", 0xFFD10E27); put("osasuna", 0xFF0A346F)
        put("celta vigo", 0xFF8AC3EE); put("rayo vallecano", 0xFFE53027); put("mallorca", 0xFFE20613)
        // Serie A
        put("juventus", 0xFF1C1C1C); put("inter", 0xFF0068A8); put("inter milan", 0xFF0068A8)
        put("ac milan", 0xFFFB090B); put("milan", 0xFFFB090B); put("napoli", 0xFF12A0D7)
        put("roma", 0xFF8E1F2F); put("as roma", 0xFF8E1F2F); put("lazio", 0xFF87D8F7)
        put("atalanta", 0xFF1E71B8); put("fiorentina", 0xFF592C82); put("bologna", 0xFFA21C26)
        put("torino", 0xFF8A1F03)
        // Ligue 1
        put("paris saint germain", 0xFF004170); put("psg", 0xFF004170); put("marseille", 0xFF2FAEE0)
        put("monaco", 0xFFE51B22); put("lyon", 0xFF1B3C86); put("lille", 0xFFE01E13); put("nice", 0xFFED1C24)
        put("rennes", 0xFFE23025); put("lens", 0xFFFCD405)
        // Primeira Liga
        put("porto", 0xFF00428C); put("benfica", 0xFFE30613); put("sl benfica", 0xFFE30613)
        put("sporting cp", 0xFF008057); put("sporting", 0xFF008057); put("braga", 0xFFB2122A)
        put("moreirense", 0xFF0A5B34); put("vitoria guimaraes", 0xFFFFFFFF)
        // Eredivisie
        put("ajax", 0xFFD2122E); put("psv", 0xFFEC1C24); put("psv eindhoven", 0xFFEC1C24)
        put("feyenoord", 0xFFDB0A13); put("az alkmaar", 0xFFEF3E42)
        // Brasileirão
        put("flamengo", 0xFFC52613); put("palmeiras", 0xFF006437); put("corinthians", 0xFF1C1C1C)
        put("sao paulo", 0xFFE30613); put("fluminense", 0xFF860A18); put("botafogo", 0xFF1C1C1C)
        put("gremio", 0xFF0D80BF); put("internacional", 0xFFE5050F); put("bahia", 0xFF0E67B4)
        put("atletico mineiro", 0xFF1C1C1C); put("cruzeiro", 0xFF0055A5); put("vasco da gama", 0xFF1C1C1C)
        put("santos", 0xFF1C1C1C); put("fortaleza", 0xFF0055A5)
        // Süper Lig
        put("galatasaray", 0xFFF9A61A); put("fenerbahce", 0xFF0A1A3F); put("besiktas", 0xFF1C1C1C)
        put("trabzonspor", 0xFF6E1231)
    }

    private val FALLBACK = longArrayOf(
        0xFF3D6DB3, 0xFFB34A4A, 0xFF3E9E7A, 0xFF8A6BB0, 0xFFB0803E,
        0xFF4A8FB0, 0xFFA33F6B, 0xFF5E874A, 0xFF9E5C3E, 0xFF556781,
    )

    fun color(name: String): Color {
        MAP[norm(name)]?.let { return Color(it) }
        val key = norm(name)
        var h = 0
        for (c in key) h = h * 31 + c.code
        return Color(FALLBACK[abs(h) % FALLBACK.size])
    }
}

package com.ahmet.edge.domain.engine

/** Tüm marketler tek skor matrisinden türer — tutarlılık garantisi. */
object Markets {

    fun oneXtwo(m: Array<DoubleArray>): Map<String, Double> {
        var h = 0.0; var d = 0.0; var a = 0.0
        for (i in m.indices) for (j in m.indices) when {
            i > j -> h += m[i][j]
            i == j -> d += m[i][j]
            else -> a += m[i][j]
        }
        return mapOf("HOME" to h, "DRAW" to d, "AWAY" to a)
    }

    fun overUnder(m: Array<DoubleArray>, line: Double): Map<String, Double> {
        var over = 0.0
        for (i in m.indices) for (j in m.indices) if (i + j > line) over += m[i][j]
        return mapOf("OVER" to over, "UNDER" to 1.0 - over)
    }

    fun btts(m: Array<DoubleArray>): Map<String, Double> {
        var yes = 0.0
        for (i in 1 until m.size) for (j in 1 until m.size) yes += m[i][j]
        return mapOf("YES" to yes, "NO" to 1.0 - yes)
    }

    fun asianHandicap(m: Array<DoubleArray>, line: Double): Map<String, Double> {
        var h = 0.0; var p = 0.0; var a = 0.0
        for (i in m.indices) for (j in m.indices) {
            val d = i - j + line
            when { d > 0 -> h += m[i][j]; d == 0.0 -> p += m[i][j]; else -> a += m[i][j] }
        }
        return mapOf("HOME" to h, "PUSH" to p, "AWAY" to a)
    }

    fun topScores(m: Array<DoubleArray>, k: Int = 5): List<Pair<String, Double>> =
        buildList {
            for (i in m.indices) for (j in m.indices) add("$i-$j" to m[i][j])
        }.sortedByDescending { it.second }.take(k)
}

package com.ahmet.edge.domain.engine

import kotlin.math.exp
import kotlin.math.ln

/** Cihazda çalışan saf matematik. Ağ gerekmez, milisaniyede biter. */
object PoissonMath {
    private const val MAX_GOALS = 10

    fun pmf(k: Int, lambda: Double): Double {
        if (lambda <= 0.0) return if (k == 0) 1.0 else 0.0
        return exp(-lambda + k * ln(lambda) - lnFactorial(k))
    }

    private val lnFactCache = DoubleArray(MAX_GOALS + 2).also {
        var acc = 0.0
        it[0] = 0.0
        for (i in 1..MAX_GOALS + 1) { acc += ln(i.toDouble()); it[i] = acc }
    }

    private fun lnFactorial(k: Int) = lnFactCache[k]

    /** Dixon-Coles tau: düşük skorlarda Poisson'un hatasını düzeltir. */
    fun tau(x: Int, y: Int, lambda: Double, mu: Double, rho: Double): Double = when {
        x == 0 && y == 0 -> 1.0 - lambda * mu * rho
        x == 0 && y == 1 -> 1.0 + lambda * rho
        x == 1 && y == 0 -> 1.0 + mu * rho
        x == 1 && y == 1 -> 1.0 - rho
        else -> 1.0
    }

    fun scoreMatrix(lambda: Double, mu: Double, rho: Double): Array<DoubleArray> {
        val n = MAX_GOALS + 1
        val m = Array(n) { DoubleArray(n) }
        var total = 0.0
        for (i in 0 until n) for (j in 0 until n) {
            val v = pmf(i, lambda) * pmf(j, mu) * tau(i, j, lambda, mu, rho)
            m[i][j] = v; total += v
        }
        for (i in 0 until n) for (j in 0 until n) m[i][j] /= total
        return m
    }
}

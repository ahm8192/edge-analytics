package com.ahmet.edge.domain.engine

import kotlin.math.abs
import kotlin.math.pow

/**
 * Marj temizleme. Ücretsiz katman "mult" kullanır, abone "shin".
 * Fark önemsiz görünür ama uzun vadede kararı değiştirir.
 */
object Devig {

    fun overround(prices: List<Double>) = prices.sumOf { 1.0 / it }

    fun marginPct(prices: List<Double>) = overround(prices) - 1.0

    fun multiplicative(prices: List<Double>): List<Double> {
        val raw = prices.map { 1.0 / it }
        val s = raw.sum()
        return raw.map { it / s }
    }

    /** p ∝ (1/o)^k, sum=1. Bisection ile k çözülür. */
    fun power(prices: List<Double>): List<Double> {
        val raw = prices.map { 1.0 / it }
        var lo = 0.5; var hi = 3.0
        repeat(80) {
            val mid = (lo + hi) / 2
            if (raw.sumOf { it.pow(mid) } > 1.0) lo = mid else hi = mid
        }
        val k = (lo + hi) / 2
        val out = raw.map { it.pow(k) }
        val s = out.sum()
        return out.map { it / s }
    }

    /** Shin: favori-longshot bias'ını teorik temelle düzeltir. */
    fun shin(prices: List<Double>): List<Double> {
        val raw = prices.map { 1.0 / it }
        val s = raw.sum()
        if (s <= 1.0) return raw.map { it / s }
        var z = 0.01
        var p = raw.map { it / s }
        repeat(200) {
            p = raw.map { r ->
                val num = kotlin.math.sqrt(z * z + 4 * (1 - z) * r * r / s)
                (num - z) / (2 * (1 - z))
            }
            val sum = p.sum()
            p = p.map { it / sum }
            val zNew = p.indices.sumOf { i ->
                (p[i] * s - raw[i]) / (p[i] * (s - 1) + 1e-12)
            } / p.size
            if (abs(zNew - z) < 1e-10) return@repeat
            z = zNew.coerceIn(1e-6, 0.5)
        }
        return p
    }

    fun fairPrice(prob: Double) = 1.0 / prob.coerceAtLeast(1e-9)
}

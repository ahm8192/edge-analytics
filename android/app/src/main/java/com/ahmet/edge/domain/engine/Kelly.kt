package com.ahmet.edge.domain.engine

import kotlin.math.roundToInt

data class StakeConfig(
    val fraction: Double = 0.25,
    val maxPctBankroll: Double = 0.02,
    val minStake: Double = 10.0,
    val roundTo: Double = 5.0,
    val maxOpenExposure: Double = 0.15
)

data class StakeResult(
    val stake: Double,
    val kellyFull: Double,
    val kellyUsed: Double,
    val pctBankroll: Double,
    val cappedBy: String?,
    val skipped: Boolean,
    val note: String?
)

object Kelly {

    fun fraction(prob: Double, price: Double): Double {
        val b = price - 1.0
        if (b <= 0) return 0.0
        return ((prob * b - (1 - prob)) / b).coerceAtLeast(0.0)
    }

    fun stake(
        prob: Double, price: Double, bankroll: Double,
        cfg: StakeConfig = StakeConfig(),
        openExposure: Double = 0.0,
        modelConfidence: Double = 1.0
    ): StakeResult {
        val full = fraction(prob, price)
        var f = full * cfg.fraction * modelConfidence
        var capped: String? = null

        if (f > cfg.maxPctBankroll) { f = cfg.maxPctBankroll; capped = "kasa limiti (%2)" }
        val room = cfg.maxOpenExposure - openExposure
        if (f > room) { f = room.coerceAtLeast(0.0); capped = "açık risk limiti" }

        val raw = bankroll * f
        if (raw < cfg.minStake) {
            return StakeResult(0.0, full, f, 0.0, capped, true,
                "Değer var ama tutar minimumun altında — geç.")
        }
        val amount = (raw / cfg.roundTo).roundToInt() * cfg.roundTo
        return StakeResult(amount, full, f, amount / bankroll, capped, false, null)
    }

    /** Kayıp serisinden sonra stake artışını yakalar (martingale koruması). */
    fun martingaleWarning(recent: List<String>, proposed: Double, avgStake: Double): String? {
        val streak = recent.reversed().takeWhile { it == "lose" }.size
        return if (streak >= 2 && proposed > avgStake * 1.5)
            "$streak maçlık kayıp serisinden sonra tutarı artırıyorsun. " +
            "Bu martingale davranışı; matematiksel olarak kasayı sıfırlar."
        else null
    }
}

package com.ahmet.edge.domain.engine

data class EdgeResult(
    val selection: String,
    val modelProb: Double,
    val marketProb: Double,
    val takenPrice: Double,
    val fairPrice: Double,
    val edgePct: Double,
    val isValue: Boolean,
    val confidence: Confidence
)

enum class Confidence { LOW, MEDIUM, HIGH }

object Edge {
    const val MIN_EDGE = 0.02

    fun compute(
        modelProbs: Map<String, Double>,
        bookPrices: Map<String, Double>,
        bestPrices: Map<String, Double> = bookPrices,
        sampleConfidence: Double = 1.0,
        useShin: Boolean = true
    ): List<EdgeResult> {
        val keys = bookPrices.keys.toList()
        val implied = if (useShin) Devig.shin(keys.map { bookPrices.getValue(it) })
                      else Devig.multiplicative(keys.map { bookPrices.getValue(it) })
        val market = keys.zip(implied).toMap()

        return modelProbs.mapNotNull { (sel, mp) ->
            val price = bestPrices[sel] ?: return@mapNotNull null
            val ev = mp * price - 1.0
            // %20 üstü "kenar" gerçek değer değil; model reytingi bu maçta piyasadan
            // sert ayrışıyor demek. Değer saymayız, güveni düşürürüz.
            val plausible = ev <= 0.20
            val conf = when {
                sampleConfidence > 0.8 && ev > 0.05 && plausible -> Confidence.HIGH
                sampleConfidence > 0.5 && ev > MIN_EDGE && plausible -> Confidence.MEDIUM
                else -> Confidence.LOW
            }
            EdgeResult(sel, mp, market[sel] ?: 0.0, price, Devig.fairPrice(mp),
                ev, ev in MIN_EDGE..0.20 && conf != Confidence.LOW, conf)
        }.sortedByDescending { it.edgePct }
    }
}

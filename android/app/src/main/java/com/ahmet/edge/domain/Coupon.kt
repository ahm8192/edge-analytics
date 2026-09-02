package com.ahmet.edge.domain

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.pow

data class CouponPick(
    val matchId: Long,
    val label: String,
    val market: String,
    val selection: String,
    val selectionLabel: String,
    val modelProb: Double,
    val price: Double,      // Pinnacle ya da kullanıcının oranı
)

data class CouponAnalysis(
    val picks: List<CouponPick>,
    val combinedProb: Double,
    val combinedOdds: Double,
    val fairOdds: Double,
    val edgePct: Double,
    val sameMatch: Boolean,
) {
    val hasValue get() = edgePct > 0.0 && !sameMatch
}

/** Uygulama ömrü boyunca kuponu tutar (in-memory). */
@Singleton
class CouponStore @Inject constructor() {
    private val _picks = MutableStateFlow<List<CouponPick>>(emptyList())
    val picks: StateFlow<List<CouponPick>> = _picks.asStateFlow()

    fun add(p: CouponPick) {
        _picks.value = _picks.value.filterNot {
            it.matchId == p.matchId && it.market == p.market
        } + p
    }

    fun remove(matchId: Long, market: String) {
        _picks.value = _picks.value.filterNot { it.matchId == matchId && it.market == market }
    }

    fun clear() { _picks.value = emptyList() }

    fun contains(matchId: Long, market: String, selection: String) =
        _picks.value.any { it.matchId == matchId && it.market == market && it.selection == selection }

    fun analyze(list: List<CouponPick> = _picks.value): CouponAnalysis {
        if (list.isEmpty())
            return CouponAnalysis(list, 0.0, 0.0, 0.0, 0.0, false)
        val cp = list.fold(1.0) { a, p -> a * p.modelProb }
        val co = list.fold(1.0) { a, p -> a * p.price }
        val fair = if (cp > 0) 1.0 / cp else 0.0
        val edge = cp * co - 1.0
        val dup = list.groupBy { it.matchId }.any { it.value.size > 1 }
        return CouponAnalysis(list, cp, co, fair, edge, dup)
    }
}

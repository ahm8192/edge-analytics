package com.ahmet.edge.billing

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf

val LocalEntitlement = compositionLocalOf { EntitlementState() }

@Composable
fun ProvideEntitlement(state: EntitlementState, content: @Composable () -> Unit) =
    CompositionLocalProvider(LocalEntitlement provides state, content = content)

/**
 * Kilitli özelliği gizleme değil, GÖSTERİP kilitleme.
 * Kullanıcı neyi kaçırdığını görmezse abone olmaz;
 * ama sahte veri de gösterilmez — kilit dürüst olmalı.
 */
@Composable
fun Gated(
    feature: Feature,
    locked: @Composable (Feature) -> Unit,
    unlocked: @Composable () -> Unit
) {
    if (LocalEntitlement.current.allows(feature)) unlocked() else locked(feature)
}

@Composable
fun rememberQuota(key: String): QuotaState {
    val e = LocalEntitlement.current
    val limit = e.quotas[key] ?: 0
    return QuotaState(key, if (limit < 0) -1 else limit, limit)
}

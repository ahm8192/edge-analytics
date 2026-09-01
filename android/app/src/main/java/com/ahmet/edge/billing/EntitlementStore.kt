package com.ahmet.edge.billing

import android.content.Context
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore by preferencesDataStore("entitlement")

/**
 * Yetki durumunun cihazdaki kopyası.
 *
 * Offline mantığı:
 *  - expiresAt geçmişse sunucudan tazele
 *  - ağ yoksa graceUntil'e kadar mevcut katman geçerli (7 gün)
 *  - grace de bittiyse FREE'ye düş; uygulama KİLİTLENMEZ, sadece daralır
 */
@Singleton
class EntitlementStore @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private object Keys {
        val TOKEN = stringPreferencesKey("token")
        val TIER = stringPreferencesKey("tier")
        val EXPIRES = longPreferencesKey("expires_at")
        val GRACE = longPreferencesKey("grace_until")
        val FLAGS = stringPreferencesKey("flags")
        val QUOTAS = stringPreferencesKey("quotas")
        val LAST_SYNC = longPreferencesKey("last_sync")
    }

    val state: Flow<EntitlementState> = context.dataStore.data.map { p ->
        val now = Instant.now().epochSecond
        val storedTier = Tier.from(p[Keys.TIER])
        val expires = p[Keys.EXPIRES] ?: 0L
        val grace = p[Keys.GRACE] ?: 0L

        val effective = when {
            now <= expires -> storedTier
            now <= grace -> storedTier          // ağsız tolerans
            else -> Tier.FREE
        }

        EntitlementState(
            tier = effective,
            storedTier = storedTier,
            isStale = now > expires,
            inGracePeriod = now > expires && now <= grace,
            expiresAt = expires,
            graceUntil = grace,
            lastSyncAt = p[Keys.LAST_SYNC] ?: 0L,
            quotas = p[Keys.QUOTAS]?.let { runCatching { Json.decodeFromString<Map<String, Int>>(it) }.getOrNull() } ?: emptyMap()
        )
    }

    suspend fun save(dto: EntitlementDto) {
        context.dataStore.edit { p ->
            p[Keys.TOKEN] = dto.token
            p[Keys.TIER] = dto.tier
            p[Keys.EXPIRES] = Instant.parse(dto.expiresAt).epochSecond
            p[Keys.GRACE] = Instant.parse(dto.graceUntil).epochSecond
            p[Keys.FLAGS] = Json.encodeToString<Map<String, Boolean>>(dto.flags)
            p[Keys.QUOTAS] = Json.encodeToString<Map<String, Int>>(dto.quotas)
            p[Keys.LAST_SYNC] = Instant.now().epochSecond
        }
    }

    suspend fun clear() = context.dataStore.edit { it.clear() }
}

data class EntitlementState(
    val tier: Tier = Tier.FREE,
    val storedTier: Tier = Tier.FREE,
    val isStale: Boolean = false,
    val inGracePeriod: Boolean = false,
    val expiresAt: Long = 0,
    val graceUntil: Long = 0,
    val lastSyncAt: Long = 0,
    val quotas: Map<String, Int> = emptyMap()
) {
    fun allows(f: Feature) = tier.covers(f.required)
    val isSubscriber get() = tier != Tier.FREE
}

@kotlinx.serialization.Serializable
data class EntitlementDto(
    val token: String,
    val tier: String,
    @kotlinx.serialization.SerialName("expires_at") val expiresAt: String,
    @kotlinx.serialization.SerialName("grace_until") val graceUntil: String,
    val flags: Map<String, Boolean> = emptyMap(),
    val quotas: Map<String, Int> = emptyMap()
)

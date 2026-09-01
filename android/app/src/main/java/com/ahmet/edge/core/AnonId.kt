package com.ahmet.edge.core

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Hesap yok. Kurulumda üretilen anonim kimlik, satın almayı kullanıcıyla
 * eşleştirmeye yeter (Play'in obfuscatedAccountId alanı).
 * Şifreli saklanır; silinirse abonelik "geri yükle" ile kurtarılır.
 */
@Singleton
class AnonId @Inject constructor(context: Context) {
    private val prefs = EncryptedSharedPreferences.create(
        context, "identity",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )

    val value: String
        get() = prefs.getString(KEY, null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString(KEY, it).apply()
        }

    private companion object { const val KEY = "anon_id" }
}

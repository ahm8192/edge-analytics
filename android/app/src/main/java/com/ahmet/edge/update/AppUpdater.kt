package com.ahmet.edge.update

import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.content.FileProvider
import com.ahmet.edge.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.util.concurrent.TimeUnit

data class UpdateInfo(
    val versionCode: Int,
    val versionName: String,
    val url: String,
    val notes: String,
    val mandatory: Boolean,
)

/**
 * Play Store yok — uygulama kendini gunceller.
 * Acilista sunucuya sorar; yeni surum varsa APK'yi indirir ve
 * sistem yukleyicisini acar. Kullanici tek "Guncelle" dokunusuyla biter.
 */
object AppUpdater {

    private val http = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    private fun base(): String =
        BuildConfig.API_BASE.trimEnd('/')

    /** Yeni surum varsa bilgisini dondurur, yoksa null. Hata yerse sessizce null. */
    suspend fun check(): UpdateInfo? = withContext(Dispatchers.IO) {
        try {
            val req = Request.Builder().url("${base()}/app/version").build()
            http.newCall(req).execute().use { r ->
                if (!r.isSuccessful) return@withContext null
                val o = JSONObject(r.body?.string() ?: return@withContext null)
                val vc = o.optInt("versionCode", 0)
                if (vc <= BuildConfig.VERSION_CODE) return@withContext null
                val url = o.optString("url").ifBlank { "${base()}/app/download" }
                UpdateInfo(
                    versionCode = vc,
                    versionName = o.optString("versionName", vc.toString()),
                    url = url,
                    notes = o.optString("notes", ""),
                    mandatory = o.optBoolean("mandatory", false),
                )
            }
        } catch (_: Exception) {
            null
        }
    }

    /** APK'yi cache'e indirir. Yuzde ilerleme geri cagirilir (0..1). */
    suspend fun download(ctx: Context, info: UpdateInfo, onProgress: (Float) -> Unit): File? =
        withContext(Dispatchers.IO) {
            try {
                val req = Request.Builder().url(info.url).build()
                http.newCall(req).execute().use { r ->
                    if (!r.isSuccessful) return@withContext null
                    val body = r.body ?: return@withContext null
                    val total = body.contentLength().takeIf { it > 0 } ?: -1L
                    val out = File(ctx.cacheDir, "update-${info.versionCode}.apk")
                    out.outputStream().use { sink ->
                        body.byteStream().use { src ->
                            val buf = ByteArray(64 * 1024)
                            var read: Int
                            var done = 0L
                            while (src.read(buf).also { read = it } != -1) {
                                sink.write(buf, 0, read)
                                done += read
                                if (total > 0) onProgress((done.toFloat() / total).coerceIn(0f, 1f))
                            }
                        }
                    }
                    onProgress(1f)
                    out
                }
            } catch (_: Exception) {
                null
            }
        }

    /** Sistem paket yukleyicisini acar. */
    fun install(ctx: Context, apk: File) {
        val uri: Uri = FileProvider.getUriForFile(
            ctx, "${ctx.packageName}.fileprovider", apk
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(intent)
    }
}

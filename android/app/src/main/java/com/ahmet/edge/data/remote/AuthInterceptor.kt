package com.ahmet.edge.data.remote

import com.ahmet.edge.core.AnonId
import okhttp3.Interceptor
import okhttp3.Response
import javax.inject.Inject

/**
 * Anonim kimlik ve yetki token'ı her isteğe eklenir.
 * Token süresi dolmuşsa sunucu 401 döner; repository tazeleyip tekrar dener.
 */
class AuthInterceptor @Inject constructor(
    private val anonId: AnonId,
    private val tokenProvider: () -> String?
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val req = chain.request().newBuilder()
            .addHeader("X-Anon-Id", anonId.value)
            .apply { tokenProvider()?.let { addHeader("Authorization", "Bearer $it") } }
            .build()
        return chain.proceed(req)
    }
}

package com.ahmet.edge.data.repo

import com.ahmet.edge.billing.*
import com.ahmet.edge.data.remote.EdgeApi
import com.ahmet.edge.data.remote.VerifyRequest
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class EntitlementRepository @Inject constructor(
    private val api: EdgeApi,
    private val store: EntitlementStore
) {
    val state: Flow<EntitlementState> = store.state

    /** Play'den satın alma geldi — sunucu Google'a sorar, biz sonucu saklarız. */
    suspend fun verify(purchaseToken: String): Boolean = runCatching {
        val r = api.verifyPurchase(VerifyRequest(purchaseToken))
        if (r.isSuccessful) { store.save(r.body()!!); true } else false
    }.getOrDefault(false)

    /** Uygulama açılışında ve öne gelişte çağrılır. Ağ yoksa sessizce geçer. */
    suspend fun refresh(): Boolean = runCatching {
        val r = api.entitlement()
        if (r.isSuccessful) { store.save(r.body()!!); true } else false
    }.getOrDefault(false)
}

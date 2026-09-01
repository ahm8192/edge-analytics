package com.ahmet.edge.billing

import android.app.Activity
import android.content.Context
import com.android.billingclient.api.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Google Play Billing sarmalayıcı.
 *
 * Kritik kurallar:
 *  1. Satın alma DOĞRULAMASI sunucuda yapılır. Buradaki Purchase nesnesi
 *     sadece "kullanıcı bir şey aldı" sinyalidir, yetki kanıtı değildir.
 *  2. acknowledge 3 gün içinde yapılmazsa Google parayı iade eder.
 *     Biz onayı sunucudan yapıyoruz (tek doğruluk kaynağı).
 *  3. onResume'da queryPurchases çağrılır: uygulama kapalıyken yapılan
 *     satın almalar veya iade edilenler böyle yakalanır.
 */
@Singleton
class BillingManager @Inject constructor(
    private val context: Context,
    private val scope: CoroutineScope,
    private val onPurchaseVerified: suspend (String) -> Unit  // purchaseToken -> sunucu
) : PurchasesUpdatedListener {

    private val _products = MutableStateFlow<List<ProductOffer>>(emptyList())
    val products: StateFlow<List<ProductOffer>> = _products.asStateFlow()

    private val _events = MutableSharedFlow<BillingEvent>(extraBufferCapacity = 8)
    val events: SharedFlow<BillingEvent> = _events.asSharedFlow()

    private val client: BillingClient = BillingClient.newBuilder(context)
        .setListener(this)
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder().enableOneTimeProducts().build()
        )
        .build()

    private var connected = false

    fun connect() {
        if (connected) return
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                connected = result.responseCode == BillingClient.BillingResponseCode.OK
                if (connected) {
                    scope.launch { loadProducts(); restorePurchases() }
                } else {
                    _events.tryEmit(BillingEvent.Error(result.debugMessage))
                }
            }
            override fun onBillingServiceDisconnected() {
                connected = false
                scope.launch { delay(2_000); connect() }   // basit yeniden bağlanma
            }
        })
    }

    suspend fun loadProducts() {
        val query = QueryProductDetailsParams.newBuilder().setProductList(
            ProductCatalog.SUBSCRIPTION_IDS.map {
                QueryProductDetailsParams.Product.newBuilder()
                    .setProductId(it)
                    .setProductType(BillingClient.ProductType.SUBS)
                    .build()
            }
        ).build()

        val result = client.queryProductDetails(query)
        val details = result.productDetailsList.orEmpty()

        _products.value = details.flatMap { pd ->
            pd.subscriptionOfferDetails.orEmpty().map { offer ->
                val phase = offer.pricingPhases.pricingPhaseList.last()
                val trial = offer.pricingPhases.pricingPhaseList
                    .firstOrNull { it.priceAmountMicros == 0L }
                ProductOffer(
                    productId = pd.productId,
                    basePlanId = offer.basePlanId,
                    offerToken = offer.offerToken,
                    offerId = offer.offerId,
                    tier = ProductCatalog.tierOf(pd.productId),
                    title = pd.title,
                    formattedPrice = phase.formattedPrice,
                    priceMicros = phase.priceAmountMicros,
                    currency = phase.priceCurrencyCode,
                    billingPeriod = phase.billingPeriod,
                    freeTrialPeriod = trial?.billingPeriod,
                    details = pd
                )
            }
        }.sortedBy { it.priceMicros }
    }

    fun launch(activity: Activity, offer: ProductOffer, anonUserId: String) {
        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                        .setProductDetails(offer.details)
                        .setOfferToken(offer.offerToken)
                        .build()
                )
            )
            // Sunucuda kullanıcıyla eşleştirmek için (dolandırıcılık tespiti)
            .setObfuscatedAccountId(anonUserId)
            .build()

        val r = client.launchBillingFlow(activity, params)
        if (r.responseCode != BillingClient.BillingResponseCode.OK) {
            _events.tryEmit(BillingEvent.Error(r.debugMessage))
        }
    }

    /** Plan değiştirme (Pro -> Elite). Google orantılı ücretlendirmeyi kendi yapar. */
    fun changePlan(activity: Activity, newOffer: ProductOffer,
                   oldPurchaseToken: String, anonUserId: String) {
        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(
                    BillingFlowParams.ProductDetailsParams.newBuilder()
                        .setProductDetails(newOffer.details)
                        .setOfferToken(newOffer.offerToken)
                        .build()
                )
            )
            .setSubscriptionUpdateParams(
                BillingFlowParams.SubscriptionUpdateParams.newBuilder()
                    .setOldPurchaseToken(oldPurchaseToken)
                    .setSubscriptionReplacementMode(
                        BillingFlowParams.SubscriptionUpdateParams
                            .ReplacementMode.CHARGE_PRORATED_PRICE
                    )
                    .build()
            )
            .setObfuscatedAccountId(anonUserId)
            .build()
        client.launchBillingFlow(activity, params)
    }

    /** Uygulama her öne geldiğinde çağrılmalı. */
    suspend fun restorePurchases() {
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.SUBS).build()
        val result = client.queryPurchasesAsync(params)
        result.purchasesList
            .filter { it.purchaseState == Purchase.PurchaseState.PURCHASED }
            .forEach { onPurchaseVerified(it.purchaseToken) }
    }

    override fun onPurchasesUpdated(result: BillingResult, purchases: MutableList<Purchase>?) {
        when (result.responseCode) {
            BillingClient.BillingResponseCode.OK -> {
                purchases?.forEach { p ->
                    when (p.purchaseState) {
                        Purchase.PurchaseState.PURCHASED ->
                            scope.launch {
                                onPurchaseVerified(p.purchaseToken)
                                _events.emit(BillingEvent.Purchased)
                            }
                        Purchase.PurchaseState.PENDING ->
                            _events.tryEmit(BillingEvent.Pending)
                    }
                }
            }
            BillingClient.BillingResponseCode.USER_CANCELED ->
                _events.tryEmit(BillingEvent.Canceled)
            BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED ->
                scope.launch { restorePurchases() }
            else -> _events.tryEmit(BillingEvent.Error(result.debugMessage))
        }
    }

    fun release() = client.endConnection()
}

data class ProductOffer(
    val productId: String,
    val basePlanId: String,
    val offerToken: String,
    val offerId: String?,
    val tier: Tier,
    val title: String,
    val formattedPrice: String,
    val priceMicros: Long,
    val currency: String,
    val billingPeriod: String,          // P1M / P1Y
    val freeTrialPeriod: String?,       // P7D vb.
    val details: ProductDetails
) {
    val isAnnual get() = billingPeriod == "P1Y"
    val hasTrial get() = freeTrialPeriod != null
}

sealed interface BillingEvent {
    data object Purchased : BillingEvent
    data object Pending : BillingEvent
    data object Canceled : BillingEvent
    data class Error(val message: String) : BillingEvent
}

object ProductCatalog {
    const val PRO = "edge_pro"
    const val ELITE = "edge_elite"
    val SUBSCRIPTION_IDS = listOf(PRO, ELITE)

    fun tierOf(productId: String) = when (productId) {
        PRO -> Tier.PRO
        ELITE -> Tier.ELITE
        else -> Tier.FREE
    }
}

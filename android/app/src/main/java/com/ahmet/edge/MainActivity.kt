package com.ahmet.edge

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.lifecycle.lifecycleScope
import com.ahmet.edge.billing.*
import com.ahmet.edge.core.AnonId
import com.ahmet.edge.data.repo.EntitlementRepository
import com.ahmet.edge.ui.EdgeNavGraph
import com.ahmet.edge.ui.theme.EdgeTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject lateinit var entitlements: EntitlementRepository
    @Inject lateinit var anonId: AnonId
    @Inject lateinit var appScope: CoroutineScope

    private lateinit var billing: BillingManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        billing = BillingManager(
            context = applicationContext,
            scope = appScope,
            onPurchaseVerified = { token -> entitlements.verify(token) }
        ).also { it.connect() }

        setContent {
            EdgeTheme {
                val entitlement by entitlements.state.collectAsState(EntitlementState())
                val offers by billing.products.collectAsState()

                ProvideEntitlement(entitlement) {
                    EdgeNavGraph(
                        offers = offers,
                        currentTier = entitlement.tier,
                        onPurchase = { offer -> billing.launch(this, offer, anonId.value) },
                        onRestore = { lifecycleScope.launch { billing.restorePurchases() } }
                    )
                    com.ahmet.edge.update.UpdateGate()
                }
            }
        }
    }

    /**
     * Öne gelişte iki şey yapılır:
     *  - Play'e sorulur (uygulama kapalıyken alınan/iade edilen abonelikler)
     *  - Sunucudan yetki tazelenir (RTDN ile değişmiş olabilir)
     */
    override fun onResume() {
        super.onResume()
        lifecycleScope.launch {
            billing.restorePurchases()
            entitlements.refresh()
        }
    }

    override fun onDestroy() {
        billing.release()
        super.onDestroy()
    }
}

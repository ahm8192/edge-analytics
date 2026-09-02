package com.ahmet.edge.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalanceWallet
import androidx.compose.material.icons.rounded.Bolt
import androidx.compose.material.icons.rounded.FormatListBulleted
import androidx.compose.material.icons.rounded.ReceiptLong
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.*
import com.ahmet.edge.billing.ProductOffer
import com.ahmet.edge.billing.Tier
import com.ahmet.edge.ui.component.Hairline
import com.ahmet.edge.ui.screen.*
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono

sealed class Dest(val route: String, val label: String, val icon: ImageVector) {
    data object Matches : Dest("matches", "MAÇLAR", Icons.Rounded.FormatListBulleted)
    data object Value : Dest("value", "DEĞER", Icons.Rounded.Bolt)
    data object Bankroll : Dest("bankroll", "KASA", Icons.Rounded.AccountBalanceWallet)
    data object Log : Dest("log", "GÜNLÜK", Icons.Rounded.ReceiptLong)
    data object Detail : Dest("match/{id}", "", Icons.Rounded.Bolt)
    data object Paywall : Dest("paywall", "", Icons.Rounded.Bolt)
    data object Coupon : Dest("coupon", "", Icons.Rounded.Bolt)

    companion object { val tabs = listOf(Matches, Value, Bankroll, Log) }
}

@Composable
fun EdgeNavGraph(
    offers: List<ProductOffer>,
    currentTier: Tier,
    onPurchase: (ProductOffer) -> Unit,
    onRestore: () -> Unit
) {
    val nav = rememberNavController()
    val entry by nav.currentBackStackEntryAsState()
    val route = entry?.destination?.route
    val showBar = route in Dest.tabs.map { it.route }

    Scaffold(
        containerColor = Ink.base,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = { if (showBar) BottomBar(nav, entry?.destination?.hierarchy) }
    ) { pad ->
        NavHost(
            nav, startDestination = Dest.Matches.route,
            modifier = Modifier.padding(pad).fillMaxSize().background(Ink.base)
        ) {
            composable(Dest.Matches.route) {
                MatchListScreen(
                    onOpen = { nav.navigate("match/$it") },
                    onUpgrade = { nav.navigate(Dest.Paywall.route) },
                    onCoupon = { nav.navigate(Dest.Coupon.route) })
            }
            composable(Dest.Value.route) {
                ValueBoardScreen(
                    onOpen = { nav.navigate("match/$it") },
                    onUpgrade = { nav.navigate(Dest.Paywall.route) })
            }
            composable(Dest.Coupon.route) {
                CouponScreen(
                    onBack = { nav.popBackStack() },
                    onOpenMatch = { nav.navigate("match/$it") })
            }
            composable(Dest.Bankroll.route) {
                BankrollScreen(onUpgrade = { nav.navigate(Dest.Paywall.route) })
            }
            composable(Dest.Log.route) {
                BetLogScreen(onUpgrade = { nav.navigate(Dest.Paywall.route) })
            }
            composable(Dest.Detail.route) {
                MatchDetailScreen(
                    onBack = { nav.popBackStack() },
                    onUpgrade = { nav.navigate(Dest.Paywall.route) })
            }
            composable(Dest.Paywall.route) {
                PaywallScreen(offers, currentTier,
                    onSelect = onPurchase, onRestore = onRestore,
                    onClose = { nav.popBackStack() })
            }
        }
    }
}

@Composable
private fun BottomBar(
    nav: androidx.navigation.NavHostController,
    hierarchy: Sequence<androidx.navigation.NavDestination>?
) {
    Column(Modifier.background(Ink.base)) {
        Hairline()
        Row(
            Modifier.fillMaxWidth().background(Ink.base)
                .navigationBarsPadding()
                .padding(top = 8.dp, bottom = 8.dp)
        ) {
            Dest.tabs.forEach { d ->
                val selected = hierarchy?.any { it.route == d.route } == true
                Column(
                    Modifier.weight(1f)
                        .clickable {
                            nav.navigate(d.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true; restoreState = true
                            }
                        }
                        .padding(vertical = 5.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        Modifier.width(20.dp).height(2.dp)
                            .background(if (selected) Ink.accent else androidx.compose.ui.graphics.Color.Transparent)
                    )
                    Spacer(Modifier.height(7.dp))
                    Icon(
                        d.icon, d.label,
                        tint = if (selected) Ink.text else Ink.faint,
                        modifier = Modifier.size(21.dp)
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        d.label, style = LabelMono.copy(fontSize = 9.sp),
                        color = if (selected) Ink.text else Ink.faint,
                        fontWeight = if (selected) FontWeight.Medium else FontWeight.Normal
                    )
                }
            }
        }
    }
}

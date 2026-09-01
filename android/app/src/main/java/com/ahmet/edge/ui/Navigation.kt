package com.ahmet.edge.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.*
import com.ahmet.edge.billing.ProductOffer
import com.ahmet.edge.billing.Tier
import com.ahmet.edge.ui.screen.*
import com.ahmet.edge.ui.theme.Ink

sealed class Dest(val route: String, val label: String, val glyph: String) {
    data object Matches : Dest("matches", "Maçlar", "▤")
    data object Value : Dest("value", "Değer", "◈")
    data object Bankroll : Dest("bankroll", "Kasa", "◑")
    data object Log : Dest("log", "Günlük", "≡")
    data object Detail : Dest("match/{id}", "", "")
    data object Paywall : Dest("paywall", "", "")

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
        bottomBar = {
            if (showBar) NavigationBar(containerColor = Ink.surface) {
                Dest.tabs.forEach { d ->
                    NavigationBarItem(
                        selected = entry?.destination?.hierarchy?.any { it.route == d.route } == true,
                        onClick = {
                            nav.navigate(d.route) {
                                popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true; restoreState = true
                            }
                        },
                        icon = { Text(d.glyph) },
                        label = { Text(d.label) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Ink.signal,
                            selectedTextColor = Ink.signal,
                            unselectedIconColor = Ink.faint,
                            unselectedTextColor = Ink.faint,
                            indicatorColor = Ink.raised
                        )
                    )
                }
            }
        }
    ) { pad ->
        NavHost(nav, startDestination = Dest.Matches.route,
                modifier = Modifier.padding(pad)) {

            composable(Dest.Matches.route) {
                MatchListScreen(
                    onOpen = { nav.navigate("match/$it") },
                    onUpgrade = { nav.navigate(Dest.Paywall.route) })
            }
            composable(Dest.Value.route) {
                ValueBoardScreen(
                    onOpen = { nav.navigate("match/$it") },
                    onUpgrade = { nav.navigate(Dest.Paywall.route) })
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

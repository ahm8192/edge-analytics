package com.ahmet.edge.ui.screen

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.LocalEntitlement
import com.ahmet.edge.data.repo.MatchRepository
import com.ahmet.edge.domain.model.Match
import com.ahmet.edge.ui.component.QuotaBanner
import com.ahmet.edge.ui.component.pct
import com.ahmet.edge.ui.component.signedPct
import com.ahmet.edge.ui.theme.Ink
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import javax.inject.Inject

@HiltViewModel
class MatchListViewModel @Inject constructor(
    private val repo: MatchRepository
) : ViewModel() {
    private val from = Instant.now()
    private val to = Instant.now().plusSeconds(7 * 86400)

    val matches: StateFlow<List<Match>> = repo.observeWindow(from, to)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val refreshing = MutableStateFlow(false)

    init { refresh() }

    fun refresh() = viewModelScope.launch {
        // Ayni anda birden fazla tazeleme calismasin (gereksiz ag trafigi).
        if (!refreshing.compareAndSet(expect = false, update = true)) return@launch
        try {
            repo.refreshWindow(from, to)
            repo.prune()
        } finally {
            refreshing.value = false
        }
    }
}

@Composable
fun MatchListScreen(
    onOpen: (Long) -> Unit,
    onUpgrade: () -> Unit,
    vm: MatchListViewModel = hiltViewModel()
) {
    val matches by vm.matches.collectAsState()
    val ent = LocalEntitlement.current
    val quota = ent.quotas["match_analysis"] ?: 0

    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        item {
            Text("Önümüzdeki 7 gün", style = MaterialTheme.typography.headlineSmall,
                color = Ink.text)
        }

        if (!ent.isSubscriber) item { QuotaBanner(quota, quota, onUpgrade) }

        if (ent.inGracePeriod) item {
            Text("Bağlantı yok — kayıtlı analizler gösteriliyor.",
                style = MaterialTheme.typography.bodySmall, color = Ink.caution)
        }

        if (matches.isEmpty()) item {
            Column(Modifier.fillMaxWidth().padding(vertical = 48.dp),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Text("Bu aralıkta maç yok.", color = Ink.muted)
                TextButton(onClick = vm::refresh) { Text("Yenile", color = Ink.signal) }
            }
        }

        items(matches, key = { it.id }) { m -> MatchRow(m, ent.allows(Feature.EDGE_DETECTION)) { onOpen(m.id) } }
    }
}

@Composable
fun MatchRow(m: Match, showEdge: Boolean, onClick: () -> Unit) {
    Surface(
        Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(10.dp), color = Ink.surface
    ) {
        Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("${m.home.shortName} – ${m.away.shortName}",
                    style = MaterialTheme.typography.titleMedium, color = Ink.text)
                Text("${m.league.name} · ${timeFmt.format(m.kickoff.atZone(ZoneId.systemDefault()))}",
                    style = MaterialTheme.typography.bodySmall, color = Ink.muted)
            }
            // Değer rozeti sadece aboneye gösterilir — ücretsizde rozet yok,
            // ama maçın kendisi ve olasılığı erişilebilir kalır.
            if (showEdge && m.hasValue && m.bestEdgePct != null) {
                Surface(color = Ink.signal.copy(alpha = 0.14f),
                    shape = RoundedCornerShape(6.dp)) {
                    Text(signedPct(m.bestEdgePct), color = Ink.signal,
                        style = MaterialTheme.typography.labelMedium,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
                }
            }
            if (m.modelConfidence < 0.6) {
                Spacer(Modifier.width(8.dp))
                Text("⚠", color = Ink.caution)
            }
        }
    }
}

@Composable
fun ValueBoardScreen(
    onOpen: (Long) -> Unit,
    onUpgrade: () -> Unit,
    vm: ValueBoardViewModel = hiltViewModel()
) {
    val ent = LocalEntitlement.current
    val matches by vm.matches.collectAsState()

    if (!ent.allows(Feature.EDGE_DETECTION)) {
        Column(Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally) {
            Text("Değer tablosu", style = MaterialTheme.typography.headlineSmall,
                color = Ink.text)
            Spacer(Modifier.height(8.dp))
            Text("Modelin piyasayı yendiği maçları tek listede toplar; " +
                 "geri kalanını elemekle başlar.",
                style = MaterialTheme.typography.bodyMedium, color = Ink.muted)
            Spacer(Modifier.height(20.dp))
            Button(onClick = onUpgrade,
                colors = ButtonDefaults.buttonColors(containerColor = Ink.signal,
                    contentColor = Ink.base)) { Text("Planları gör") }
        }
        return
    }

    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Column {
                Text("Değer tablosu", style = MaterialTheme.typography.headlineSmall,
                    color = Ink.text)
                Text("Kenar payına göre sıralı. %2 altı gürültüdür, listeye girmez.",
                    style = MaterialTheme.typography.bodySmall, color = Ink.muted)
            }
        }
        items(matches, key = { it.id }) { m -> MatchRow(m, true) { onOpen(m.id) } }
        if (matches.isEmpty()) item {
            Text("Şu anda değerli maç yok. Bu iyi bir haber — zorlama bahis yok.",
                color = Ink.muted, modifier = Modifier.padding(vertical = 40.dp))
        }
    }
}

@HiltViewModel
class ValueBoardViewModel @Inject constructor(repo: MatchRepository) : ViewModel() {
    val matches = repo.observeValueBoard()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
}

private val timeFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("d MMM HH:mm")

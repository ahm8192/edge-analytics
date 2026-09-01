package com.ahmet.edge.ui.component

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.unit.dp
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.ui.theme.Ink

/**
 * Kilitli özellik gösterimi.
 * Sahte sayı GÖSTERMEZ. Bulanık gerçek veri de göstermez — o aldatıcıdır.
 * Sadece neyin var olduğunu ve neye yaradığını söyler.
 */
@Composable
fun LockedCard(feature: Feature, onUpgrade: () -> Unit, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxWidth().clickable(onClick = onUpgrade),
        shape = RoundedCornerShape(10.dp),
        color = Ink.surface,
        border = androidx.compose.foundation.BorderStroke(1.dp, Ink.line)
    ) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Box(
                Modifier.size(34.dp)
                    .background(Ink.brass.copy(alpha = 0.12f), RoundedCornerShape(8.dp)),
                contentAlignment = Alignment.Center
            ) { Text("◆", color = Ink.brass) }

            Column(Modifier.weight(1f)) {
                Text(feature.title, style = MaterialTheme.typography.titleMedium,
                    color = Ink.text)
                if (feature.blurb.isNotEmpty()) {
                    Spacer(Modifier.height(2.dp))
                    Text(feature.blurb, style = MaterialTheme.typography.bodySmall,
                        color = Ink.muted)
                }
            }
            Text(feature.required.name, color = Ink.brass,
                style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
fun QuotaBanner(remaining: Int, limit: Int, onUpgrade: () -> Unit) {
    if (limit < 0) return
    val exhausted = remaining <= 0
    Surface(
        Modifier.fillMaxWidth(), shape = RoundedCornerShape(8.dp),
        color = if (exhausted) Ink.caution.copy(alpha = 0.10f) else Ink.raised
    ) {
        Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (exhausted) "Günlük analiz hakkın doldu. Yarın sıfırlanır."
                else "Bugün $remaining analiz hakkın kaldı",
                style = MaterialTheme.typography.bodySmall,
                color = if (exhausted) Ink.caution else Ink.muted,
                modifier = Modifier.weight(1f)
            )
            TextButton(onClick = onUpgrade) {
                Text("Sınırsıza geç", color = Ink.brass,
                    style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}

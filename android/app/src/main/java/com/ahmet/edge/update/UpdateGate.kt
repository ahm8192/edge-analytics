package com.ahmet.edge.update

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import com.ahmet.edge.ui.component.PrimaryButton
import com.ahmet.edge.ui.theme.DataStyle
import com.ahmet.edge.ui.theme.Ink
import com.ahmet.edge.ui.theme.LabelMono
import kotlinx.coroutines.launch

/**
 * Acilista sessizce guncelleme kontrol eder; varsa temali bir kart gosterir.
 * Uygulama akisini engellemez (zorunlu surum haric).
 */
@Composable
fun UpdateGate() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var info by remember { mutableStateOf<UpdateInfo?>(null) }
    var dismissed by remember { mutableStateOf(false) }
    var progress by remember { mutableStateOf<Float?>(null) }

    LaunchedEffect(Unit) { info = AppUpdater.check() }

    val u = info ?: return
    if (dismissed && !u.mandatory) return

    Dialog(onDismissRequest = { if (!u.mandatory) dismissed = true }) {
        Column(
            Modifier
                .clip(RoundedCornerShape(10.dp))
                .background(Ink.surface)
                .border(1.dp, Ink.lineStrong, RoundedCornerShape(10.dp))
                .padding(20.dp)
        ) {
            Text("GÜNCELLEME", style = LabelMono, color = Ink.accent)
            Spacer(Modifier.height(10.dp))
            Text(
                "Yeni sürüm ${u.versionName}",
                style = MaterialTheme.typography.titleLarge, color = Ink.text
            )
            if (u.notes.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(u.notes, style = MaterialTheme.typography.bodyMedium, color = Ink.muted)
            }
            Spacer(Modifier.height(18.dp))

            val p = progress
            if (p == null) {
                PrimaryButton("İndir ve kur", onClick = {
                    progress = 0f
                    scope.launch {
                        val apk = AppUpdater.download(ctx, u) { progress = it }
                        if (apk != null) AppUpdater.install(ctx, apk)
                        else progress = null
                    }
                })
                if (!u.mandatory) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Sonra", style = MaterialTheme.typography.labelLarge, color = Ink.muted,
                        modifier = Modifier
                            .align(Alignment.CenterHorizontally)
                            .clip(RoundedCornerShape(6.dp))
                            .clickable { dismissed = true }
                            .padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                }
            } else {
                Box(
                    Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp))
                        .background(Ink.raised)
                ) {
                    Box(
                        Modifier.fillMaxWidth(p.coerceIn(0f, 1f)).fillMaxHeight()
                            .background(Ink.accent, RoundedCornerShape(3.dp))
                    )
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    if (p >= 1f) "Yükleyici açılıyor…" else "İndiriliyor  ${(p * 100).toInt()}%",
                    style = DataStyle.copy(fontWeight = FontWeight.Medium), color = Ink.muted
                )
            }
        }
    }
}

package com.ahmet.edge.ui.screen

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.ahmet.edge.billing.Feature
import com.ahmet.edge.billing.ProductOffer
import com.ahmet.edge.billing.Tier
import com.ahmet.edge.ui.theme.Ink

/**
 * Paywall yazımı ilkesi: özellik listesi satmıyoruz, SONUÇ satıyoruz.
 * "Kalibre olasılık" kullanıcıya bir şey ifade etmez.
 * "Modelin %70 dediğinde gerçekten %70 çıkması" eder.
 */
@Composable
fun PaywallScreen(
    offers: List<ProductOffer>,
    currentTier: Tier,
    onSelect: (ProductOffer) -> Unit,
    onRestore: () -> Unit,
    onClose: () -> Unit
) {
    var selected by remember(offers) {
        mutableStateOf(offers.firstOrNull { it.isAnnual } ?: offers.firstOrNull())
    }

    Column(
        Modifier.fillMaxSize().background(Ink.base)
            .statusBarsPadding()
            .navigationBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(20.dp, 12.dp, 20.dp, 32.dp),
        verticalArrangement = Arrangement.spacedBy(20.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("Tahminden karara geç",
                    style = MaterialTheme.typography.displaySmall, color = Ink.text)
                Spacer(Modifier.height(6.dp))
                Text(
                    "Ücretsiz sürüm maçın olasılığını verir. Abonelik, o olasılığın " +
                    "oranı yenip yenmediğini ve ne kadar yatırman gerektiğini söyler.",
                    style = MaterialTheme.typography.bodyMedium, color = Ink.muted
                )
            }
            TextButton(onClick = onClose) { Text("Kapat", color = Ink.faint) }
        }

        ValueRow("Değer tespiti",
            "Modelin piyasadan daha iyi olduğu maçları işaretler. Diğerlerini oynamamanı söyler.")
        ValueRow("Kelly tutar önerisi",
            "Ne kadar yatıracağını kasana ve kenarına göre hesaplar. Sezgiyle değil.")
        ValueRow("CLV takibi",
            "Kapanış oranını yenip yenmediğini ölçer. Kârdan daha dürüst bir başarı göstergesi.")
        ValueRow("Kadro ve bağlam düzeltmesi",
            "Sakat oyuncu, hakem profili, fikstür yoğunluğu, hava — hepsi olasılığa işlenir.")

        Spacer(Modifier.height(4.dp))

        offers.forEach { offer ->
            PlanCard(
                offer = offer,
                isSelected = selected?.offerToken == offer.offerToken,
                isCurrent = currentTier == offer.tier,
                monthlyReference = offers.firstOrNull { it.tier == offer.tier && !it.isAnnual },
                onClick = { selected = offer }
            )
        }

        Button(
            onClick = { selected?.let(onSelect) },
            enabled = selected != null,
            modifier = Modifier.fillMaxWidth().height(52.dp),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Ink.signal, contentColor = Ink.base)
        ) {
            Text(
                if (selected?.hasTrial == true) "Ücretsiz denemeyi başlat"
                else "Aboneliği başlat",
                fontWeight = FontWeight.SemiBold
            )
        }

        Text(
            "Abonelik seçtiğin dönemin sonunda otomatik yenilenir. " +
            "Google Play hesabından istediğin an iptal edebilirsin; " +
            "iptalden sonra ödediğin dönemin sonuna kadar erişimin sürer.",
            style = MaterialTheme.typography.bodySmall, color = Ink.faint
        )

        TextButton(onClick = onRestore, Modifier.align(Alignment.CenterHorizontally)) {
            Text("Satın alımları geri yükle", color = Ink.muted)
        }

        HorizontalDivider(color = Ink.line)

        Text(
            "Bu uygulama istatistiksel analiz aracıdır. Kazanç garantisi vermez ve " +
            "hiçbir bahsi sana oynatmaz. Modelin doğru çalıştığı durumda bile uzun " +
            "kayıp serileri normaldir.",
            style = MaterialTheme.typography.bodySmall, color = Ink.faint
        )
    }
}

@Composable
private fun ValueRow(title: String, body: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.padding(top = 6.dp).size(6.dp)
            .background(Ink.signal, RoundedCornerShape(3.dp)))
        Column {
            Text(title, style = MaterialTheme.typography.titleMedium, color = Ink.text)
            Text(body, style = MaterialTheme.typography.bodySmall, color = Ink.muted)
        }
    }
}

@Composable
private fun PlanCard(
    offer: ProductOffer,
    isSelected: Boolean,
    isCurrent: Boolean,
    monthlyReference: ProductOffer?,
    onClick: () -> Unit
) {
    val saving = if (offer.isAnnual && monthlyReference != null) {
        val yearlyIfMonthly = monthlyReference.priceMicros * 12
        val pct = 100 - (offer.priceMicros * 100 / yearlyIfMonthly)
        if (pct > 0) "%$pct tasarruf" else null
    } else null

    Surface(
        Modifier.fillMaxWidth().clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = if (isSelected) Ink.raised else Ink.surface,
        border = BorderStroke(if (isSelected) 1.5.dp else 1.dp,
            if (isSelected) Ink.signal else Ink.line)
    ) {
        Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(offer.tier.name, style = MaterialTheme.typography.titleMedium,
                        color = Ink.text)
                    if (saving != null) {
                        Surface(color = Ink.brass.copy(alpha = 0.15f),
                            shape = RoundedCornerShape(4.dp)) {
                            Text(saving, color = Ink.brass,
                                style = MaterialTheme.typography.labelMedium,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                        }
                    }
                    if (isCurrent) Text("mevcut planın", color = Ink.faint,
                        style = MaterialTheme.typography.labelMedium)
                }
                Text(if (offer.isAnnual) "Yıllık" else "Aylık",
                    style = MaterialTheme.typography.bodySmall, color = Ink.muted)
                offer.freeTrialPeriod?.let {
                    Text("${trialDays(it)} gün ücretsiz deneme",
                        style = MaterialTheme.typography.bodySmall, color = Ink.signal)
                }
            }
            Text(offer.formattedPrice, style = MaterialTheme.typography.headlineSmall,
                color = Ink.text)
        }
    }
}

private fun trialDays(iso: String): Int =
    Regex("P(\\d+)D").find(iso)?.groupValues?.get(1)?.toIntOrNull()
        ?: Regex("P(\\d+)W").find(iso)?.groupValues?.get(1)?.toIntOrNull()?.times(7)
        ?: 0

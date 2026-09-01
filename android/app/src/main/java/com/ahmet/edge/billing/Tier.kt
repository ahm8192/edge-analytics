package com.ahmet.edge.billing

/**
 * Katmanlar ve özellik haritası.
 * Bu dosya sunucudaki backend/app/billing/tiers.py ile AYNI olmalı.
 * İstemcideki bayraklar sadece UI içindir; gerçek kapı sunucudadır.
 */
enum class Tier(val rank: Int) {
    FREE(0), PRO(1), ELITE(2);

    fun covers(required: Tier) = rank >= required.rank

    companion object {
        fun from(value: String?) = entries.firstOrNull { it.name == value } ?: FREE
    }
}

enum class Feature(val required: Tier, val title: String, val blurb: String) {
    // Ücretsiz çekirdek
    BASIC_1X2(Tier.FREE, "Maç sonucu olasılığı", "Dixon-Coles ile 1/X/2 dağılımı"),
    BASIC_FORM(Tier.FREE, "Form", "Zaman ağırlıklı son maç performansı"),
    SINGLE_BOOK_DEVIG(Tier.FREE, "Adil oran", "Tek kitaptan marj temizleme"),

    // Pro
    ALL_MARKETS(Tier.PRO, "Tüm marketler", "Alt/üst, handikap, KG var, doğru skor"),
    ENSEMBLE_MODEL(Tier.PRO, "Birleşik model", "Dixon-Coles + Elo + GBDT ortalaması"),
    CALIBRATED_PROB(Tier.PRO, "Kalibre olasılık", "%70 dediğinde gerçekten %70"),
    EDGE_DETECTION(Tier.PRO, "Değer tespiti", "Modelin piyasayı yendiği maçlar"),
    KELLY_STAKE(Tier.PRO, "Kelly bahis tutarı", "Çeyrek Kelly ile miktar önerisi"),
    BANKROLL_MANAGER(Tier.PRO, "Kasa yönetimi", "Açık risk ve limit takibi"),
    BET_LOG(Tier.PRO, "Bahis günlüğü", "Her tahmin kaydedilir ve denetlenir"),
    CLV_TRACKING(Tier.PRO, "CLV takibi", "Kapanış oranını yenip yenmediğin"),
    ODDS_MOVEMENT(Tier.PRO, "Oran hareketi", "Açılıştan kapanışa oran eğrisi"),
    SQUAD_ADJUSTMENT(Tier.PRO, "Kadro düzeltmesi", "Sahaya çıkan 11'e göre güç"),
    INJURY_IMPACT(Tier.PRO, "Sakatlık etkisi", "Eksik oyuncunun gol beklentisine etkisi"),
    CONTEXT_ADJUST(Tier.PRO, "Bağlam düzeltmesi", "Hakem, hava, rakım, fikstür yoğunluğu"),
    VALUE_ALERTS(Tier.PRO, "Değer bildirimi", "Fırsat oluştuğunda anlık uyarı"),
    NO_ADS(Tier.PRO, "Reklamsız", ""),

    // Elite
    MULTI_BOOK_COMPARE(Tier.ELITE, "Oran karşılaştırma", "Tüm kitaplarda en iyi oran"),
    SHARP_MOVE_SIGNAL(Tier.ELITE, "Keskin para sinyali", "Anlamlı oran hareketi tespiti"),
    MODEL_EXPLAIN(Tier.ELITE, "Model açıklaması", "Hangi etken olasılığı ne kadar değiştirdi"),
    MONTE_CARLO(Tier.ELITE, "Risk simülasyonu", "10.000 senaryoda kasa seyri"),
    BACKTEST_LAB(Tier.ELITE, "Geriye test", "Kendi stratejini walk-forward test et"),
    CORRELATION_CHECK(Tier.ELITE, "Kombine denetimi", "Korelasyonlu ayak uyarısı"),
    PORTFOLIO_BREAKDOWN(Tier.ELITE, "Performans dökümü", "Lig ve market bazında sonuç"),
    DATA_EXPORT(Tier.ELITE, "Dışa aktarma", "CSV ve API erişimi"),
    CUSTOM_MODEL_WEIGHTS(Tier.ELITE, "Özel ağırlıklar", "Kendi model ağırlığını kur");
}

data class QuotaState(val key: String, val remaining: Int, val limit: Int) {
    val isUnlimited get() = limit < 0
    val isExhausted get() = !isUnlimited && remaining <= 0
}

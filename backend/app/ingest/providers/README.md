# Sağlayıcı adaptörü yazmak

`GenericStatsProvider` bir şablondur; gerçek sağlayıcın için kopyala ve
üç şeyi düzelt:

1. `base_url`, `auth_style`, `auth_key_name`
2. `FIELD_MAP` / `SHOT_MAP` — noktalı yol sözdizimi iç içe JSON'u okur
3. `capabilities` — neyi verebildiği; orkestratör buna göre yönlendirir

Kodun geri kalanına dokunma. Uzlaştırma, hız sınırı, yeniden deneme,
köken kaydı ve takım eşleme taban sınıfta hazır.

## Sağlayıcı seçerken bakılacaklar

| Kriter | Neden |
|---|---|
| Olay bazlı veri var mı | Maç toplamı yeterli değil (madde 2) |
| xG modeli hangisi | Sağlayıcı değişince xG kırılır (madde 47) |
| Oran geçmişi | Kapanış oranı olmadan CLV hesaplanamaz (madde 76) |
| Gecikme | 15 dakika gecikmeli oran işe yaramaz |
| Kota | `scheduler.estimate_daily_calls()` ile hesapla |
| Kadro yayın saati | Maçtan kaç dakika önce açıklanıyor (madde 8) |

## En az iki sağlayıcı

Tek sağlayıcı sessizce bozulduğunda haberin olmaz. İkinci sağlayıcı
maliyeti değil, `source_conflict` tablosundaki çelişki sayısı sana
verinin ne zaman bozulduğunu söyler.

İkinci sağlayıcı bedava bir kaynak bile olabilir — amaç doğrulama,
zenginlik değil.

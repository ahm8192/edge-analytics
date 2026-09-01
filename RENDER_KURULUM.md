# Render ile Edge Analytics backend yayına alma

Backend artık senin bilgisayarında değil, Render'ın ücretsiz sunucusunda çalışır.
Telefon herhangi bir ağdayken (mobil veri dahil) veriye erişir, bilgisayarın
açık olması gerekmez.

## 0. Ön hazırlık (bu repoda yapıldı)

- `render.yaml` Render'ın okuduğu tanım dosyası (Docker, free plan, `/health`).
- `live_data.py` football-data.org limitine (dakikada 10 istek) dayanıklı hale
  getirildi: sonuç önbelleği, istekler arası bekleme, 429'da tekrar deneme.
- `.gitignore` ile `.env` ve `*.apk` repoya **girmez**. Token gizli kalır.
- Başlangıç lig seti: `PL,BL1,SA`. Sorunsuz çalışınca Render panelinden artır.

## 1. Kodu GitHub'a gönder

GitHub'da boş bir repo aç (README ekleme). Sonra proje klasöründe:

```bash
git remote add origin https://github.com/KULLANICI_ADIN/edge-analytics.git
git push -u origin main
```

`.env` dosyasının push edilmediğini `git ls-files | grep env` ile doğrula —
yalnızca `.env.example` görünmeli.

## 2. Render'da servisi oluştur

1. https://dashboard.render.com → **New + → Blueprint**.
2. GitHub reposunu seç. Render `render.yaml`'ı bulur ve `edge-analytics-api`
   servisini gösterir. **Apply** de.
3. Render `FOOTBALL_DATA_TOKEN` değerini sorar (`sync: false` olduğu için).
   football-data.org panelinden **yenilediğin** tokenı yapıştır.
   (Eski token sohbette paylaşıldı, mutlaka yenile.)
4. İlk build + deploy 3-5 dakika sürer. Bitince yeşil "Live" yazar.

## 3. Çalıştığını doğrula

Render sana bir URL verir, örn: `https://edge-analytics-api-xxxx.onrender.com`

Tarayıcıdan sırayla aç:

```
https://edge-analytics-api-xxxx.onrender.com/health
    -> {"status":"ok"}

https://edge-analytics-api-xxxx.onrender.com/v1/matches?from=2026-09-01&to=2026-09-08
    -> icinde "matches", "leagues", "teams" olan JSON
```

Not: Ücretsiz plan 15 dk hareketsizlikte servisi uyutur. Uykudan sonraki
**ilk istek 30-60 sn** sürer (cold start), sonra hızlanır.

## 4. APK'yı yeni adrese göre yeniden derle

Android projesinde (`android/` klasörü, bu repoda değil):

```bash
./gradlew :app:assembleDebug -PAPI_BASE=https://edge-analytics-api-xxxx.onrender.com/
```

Sondaki `/` kalsın. Artık HTTPS olduğu için:
- aynı Wi-Fi şartı yok,
- Windows firewall ayarı yok,
- cleartext (şifresiz HTTP) izni gerekmez.

Yeni APK: `android/app/build/outputs/apk/debug/app-debug.apk` — telefona kur.

Uygulamanın ilk açılışında Render cold start yüzünden 1 deneme boşa gidebilir;
uygulamada HTTP timeout ayarı varsa 60 sn'ye çıkarmak iyi olur.

## 5. Sonradan lig eklemek

Render panel → servis → **Environment** → `FOOTBALL_DATA_COMPETITIONS` değerini
`PL,BL1,SA,PD,FL1` gibi genişlet → **Save**, servis otomatik yeniden başlar.
Çok lig eklersen cold start'ta ilk `/v1/matches` yavaşlar (her lig ~1.5 sn) ve
football-data limiti yeniden devreye girebilir; `FOOTBALL_DATA_CACHE_TTL`'i
artırmak (örn. `300`) yükü azaltır.

## Kod güncellemesi

Backend'de değişiklik yapınca `git push` yeter; Render otomatik yeniden deploy eder.

## football-data.org ücretsiz plan sınırları

- Dakikada 10 istek.
- Canlı skor ve bahis oranı **yok**; fikstür ve gecikmeli skor var.
- Bu yüzden `/v1/matches/{id}/odds` boş `[]`, analiz nötr öncül döndürür.

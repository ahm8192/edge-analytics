# Local Docker ile Edge Analytics kurulumu

Bu kurulumda backend kullanıcının bilgisayarında Docker içinde çalışır. Android telefon ve bilgisayar aynı Wi‑Fi ağında olmalıdır. Bilgisayar kapanırsa uygulama canlı veri alamaz.

## 1. Projeyi hazırlayın

Arşivi açtıktan sonra terminali proje klasöründe açın. `.env.example` dosyasını `.env` adıyla kopyalayın ve `FOOTBALL_DATA_TOKEN` değerine football-data.org hesabınızdaki tokenı yazın. Tokenı GitHub’a veya APK’ya koymayın.

```bash
cp .env.example .env
```

## 2. Backend’i başlatın

```bash
docker compose up --build -d
```

Çalıştığını kontrol etmek için bilgisayarda şu adresi açın:

```text
http://localhost:8000/health
```

Yanıt `{"status":"ok"}` olmalıdır. Logları görmek için `docker compose logs -f edge-api` komutunu kullanın.

## 3. Bilgisayarın yerel IP adresini öğrenin

Windows’ta Komut İstemi’ni açıp `ipconfig` yazın ve aktif Wi‑Fi bağdaştırıcısındaki IPv4 adresini bulun. Örnek: `192.168.1.25`. Linux/macOS’ta `hostname -I` veya `ifconfig` kullanılabilir.

Telefon ve bilgisayar aynı Wi‑Fi ağında olmalıdır. Telefonda tarayıcıdan `http://192.168.1.25:8000/health` adresini açın. Sağlık yanıtını görüyorsanız ağ bağlantısı tamamdır. Görmüyorsanız Windows Güvenlik Duvarı’nda TCP 8000 portuna izin verin.

## 4. Android APK’yı PC adresiyle derleyin

Android projesini Android Studio ile açın veya terminalde `android` klasörüne girin. Aşağıdaki komutta `192.168.1.25` yerine kendi PC IPv4 adresinizi yazın:

```bash
./gradlew :app:assembleDebug -PAPI_BASE=http://192.168.1.25:8000/
```

APK şu konumda oluşur:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

APK’yı telefona kurun. Backend açık olduğu sürece uygulama maç verilerini API’den alacaktır.

## Emulator kullanıyorsanız

Android Studio emulator’ünde host bilgisayara erişmek için genellikle şu adres kullanılır:

```bash
./gradlew :app:assembleDebug -PAPI_BASE=http://10.0.2.2:8000/
```

Gerçek telefonda `10.0.2.2` yerine bilgisayarın Wi‑Fi IPv4 adresi kullanılmalıdır.

## Güvenlik notu

API tokenı sohbet içinde paylaşıldığı için football-data.org panelinden yenilemeniz önerilir. Yeni tokenı yalnızca `.env` dosyasına yazın. Ücretsiz football-data.org planı canlı skor ve bahis oranı sağlamaz; fikstür ve gecikmeli skor sunar.

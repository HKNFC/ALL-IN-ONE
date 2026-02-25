# Evrensel Borsa Tarayıcı - BIST + ABD Borsaları

## 🌍 Genel Bakış

Bu sistem, Mark Minervini'nin Trend Template ve VCP metodolojisini **BIST (Borsa İstanbul)** ve **ABD Borsaları (NYSE, NASDAQ)** üzerinde eş zamanlı uygular.

## 🎯 Uygulanan Kriterler

### 1. Evrensel Trend Filtresi (Aşama 2)

#### 📊 Teknik Kriterler:
- ✅ Mevcut Fiyat > 150 günlük SMA
- ✅ Mevcut Fiyat > 200 günlük SMA
- ✅ 200 günlük SMA en az 30 gündür yukarı eğilimli

#### 📈 Relative Strength (RS):
- **ABD:** IBD tarzı RS > 80 (S&P 500'e göre)
- **BIST:** Son 3 ayda XU100'e göre pozitif ayrışma

### 2. VCP ve Giriş Hassasiyeti

#### 🔍 VCP Tespiti:
- Son 10 haftalık taban oluşumunu analiz eder
- Volatilite daralması: %30 → %10 → %3
- En az 2 daralma tespit eder
- "Tightness" (sıkışma) seviyesi %3'ün altı

#### 📍 Pivot Noktası:
- 20 günlük en yüksek seviye
- Pivot'a uzaklık hesaplanır
- Konsolidasyon bölgesi izlenir

### 3. Piyasa Bazlı Dinamik Sinyaller

#### 🇺🇸 ABD İçin:
- **Hacim Kuruması:** Son 50 günlük ortalamanın %50 altına düşmesi
- VCP sırasında hacim azalması beklenir

#### 🇹🇷 BIST İçin:
- **Pozitif RS Ayrışması:** XU100'ü 3 aylık bazda geçmeli
- Enflasyonist ortam gözetilir

### 4. Çıktı Formatı

Her hisse için:
```
[BORSA] - [HİSSE_KODU] - [DURUM]
```

**Durum Seviyeleri:**
- 🚀 **BREAKOUT:** Pivot'u hacimli kırdı (ALIM SİNYALİ)
- ⭐ **PIVOT_NEAR:** Pivot'a %1'den yakın (YAKIN TAKİP)
- 📊 **SETUP:** VCP var, pivot'tan biraz uzak (İZLE)
- 👀 **WATCHING:** Kriterleri karşılıyor (RADAR)

---

## 🚀 Kullanım

### 1. Universal Scanner (Tarama)

```bash
python3 universal_scanner.py
```

**Ne yapar?**
- ABD'de ~150 hisse tarar
- BIST'te ~70 hisse tarar
- Tüm kriterleri uygular
- Sonuçları duruma göre sınıflandırır

**Çıktılar:**
- `universal_scan_YYYYMMDD_HHMMSS.csv` - Tüm sonuçlar
- `breakout_watchlist_YYYYMMDD_HHMMSS.csv` - BREAKOUT + PIVOT_NEAR hisseler

**Örnek Çıktı:**
```
🇺🇸 US - NVDA - PIVOT_NEAR
   Fiyat: $185.48 | Pivot: $187.50 | Mesafe: 1.08%
   RS: 92.15 | VCP: 3 daralma (TIGHT)
   Stop: $172.50 (-7%)

🇹🇷 BIST - GARAN - SETUP
   Fiyat: ₺45.80 | Pivot: ₺47.20 | Mesafe: 2.97%
   RS Ayrışma: +12.34% | VCP: 2 daralma (FORMING)
   Stop: ₺42.59 (-7%)
```

---

### 2. Breakout Alert (Anlık Uyarılar)

```bash
python3 breakout_alert.py
```

**Ne yapar?**
- Watchlist'teki hisseleri her 5 dakikada kontrol eder
- Pivot kırılımlarını tespit eder (Hacim > 1.5x)
- Stop-loss seviyesine düşüşleri izler
- Telegram'dan anlık uyarı gönderir

**Telegram Mesaj Örnekleri:**

#### 💰 ALIM SİNYALİ
```
💰 ALIM SİNYALİ

MINERVINI BUY ALERT

🇺🇸 US - NVDA

✅ Pivot Kırıldı!
Fiyat: $188.50
Pivot: $187.50
Hacim: 2.3x (Normal: 1.0x)

📊 ALIM BİLGİLERİ:
Giriş: $188.50
Stop: $175.30 (-7%)
Risk: $13.20

⚠️ Stop-loss'u mutlaka kullanın!
```

#### 🔴 SATIM SİNYALİ
```
🔴 SATIM SİNYALİ

EXIT SIGNAL

🇹🇷 BIST - GARAN

❌ Stop-Loss Seviyesi!
Fiyat: ₺42.50
Stop: ₺42.59
Zarar: -7.00%

⚠️ Derhal pozisyonu kapat!
```

---

## ⚙️ Kurulum

### Adım 1: Universal Scan Çalıştır

```bash
python3 universal_scanner.py
```

**Sonuç:** 
- `universal_scan_*.csv` dosyası oluşur
- `breakout_watchlist_*.csv` dosyası oluşur (BREAKOUT + PIVOT_NEAR)

### Adım 2: Breakout Alert Kur

```bash
python3 breakout_alert.py
```

İlk çalıştırmada:
1. `breakout_config.json` oluşturulur
2. Telegram bilgilerini girin:
```json
{
  "telegram_enabled": true,
  "telegram_bot_token": "123456:ABCdef...",
  "telegram_chat_id": "987654321",
  "volume_spike_threshold": 1.5,
  "stop_loss_pct": 7.0,
  "check_interval_minutes": 5,
  "market_hours_only": false
}
```

3. `breakout_watchlist.csv` otomatik yüklenir (son scan'den)

### Adım 3: Sürekli İzleme Başlat

```bash
python3 breakout_alert.py
# Seçenek 2: Sürekli izleme
```

---

## 📊 Workflow Özeti

```
1. Universal Scanner ile BIST + ABD taraması
   ↓
2. BREAKOUT ve PIVOT_NEAR hisseler watchlist'e eklenir
   ↓
3. Breakout Alert sürekli izlemeye başlar
   ↓
4. Pivot kırılımlarında ALIM sinyali
   ↓
5. Stop-loss seviyesinde SATIM sinyali
   ↓
6. Telegram'dan anlık bildirimler al
```

---

## 🎯 Önemli Parametreler

### Volume Spike Threshold
```json
"volume_spike_threshold": 1.5
```
- Breakout için gereken minimum hacim çarpanı
- 1.5x = Normal hacmin %50 fazlası
- Daha katı: 2.0x, Daha esnek: 1.2x

### Check Interval
```json
"check_interval_minutes": 5
```
- Ne kadar sıklıkla kontrol edilecek
- Önerilen: 5-15 dakika arası
- Çok kısa: API limitleri
- Çok uzun: Geç kalabilirsiniz

### Market Hours Only
```json
"market_hours_only": false
```
- `true`: Sadece piyasa saatlerinde kontrol
- `false`: 7/24 kontrol (önerilen)

### Stop Loss Percentage
```json
"stop_loss_pct": 7.0
```
- Giriş fiyatından stop-loss mesafesi
- Minervini standardı: %7
- Değiştirmek önerilmez

---

## 🔧 İleri Seviye Kullanım

### Manuel Watchlist Oluşturma

`breakout_watchlist.csv` dosyasını manuel düzenleyebilirsiniz:

```csv
Market,Ticker,Price,Pivot,Stop_Level,Status
US,NVDA,185.48,187.50,172.50,PIVOT_NEAR
US,AMD,150.25,155.00,139.73,SETUP
BIST,GARAN,45.80,47.20,42.59,PIVOT_NEAR
BIST,THYAO,310.50,315.00,288.77,SETUP
```

### Sadece BIST veya ABD Taraması

`universal_scanner.py` dosyasında `main()` fonksiyonunu düzenleyin:

```python
# Sadece ABD
scanner.us_tickers = scanner.get_us_tickers()
scanner.bist_tickers = []

# Sadece BIST
scanner.us_tickers = []
scanner.bist_tickers = scanner.get_bist_tickers()
```

### Hisse Listesi Özelleştirme

`universal_scanner.py` içinde:

```python
def get_us_tickers(self):
    # Kendi hisse listenizi ekleyin
    return ['AAPL', 'MSFT', 'GOOGL', ...]

def get_bist_tickers(self):
    # BIST hisselerinizi ekleyin
    bist_codes = ['AKBNK', 'GARAN', 'THYAO', ...]
    return [f"{code}.IS" for code in bist_codes]
```

---

## 📱 Telegram Bot Kurulumu

Eğer daha önce telegram bot kurmadıysanız:

### 1. Bot Oluştur
- @BotFather'ı aç
- `/newbot` gönder
- Bot adı ver
- Bot kullanıcı adı ver
- **Token'ı kopyala**

### 2. Chat ID Öğren
- @userinfobot'u aç
- **Chat ID'ni kopyala**

### 3. Config'e Ekle
```json
{
  "telegram_bot_token": "BURAYA_TOKEN",
  "telegram_chat_id": "BURAYA_CHAT_ID",
  ...
}
```

---

## 🚨 Önemli Notlar

### 1. Stop-Loss Disiplini
- **Her zaman** %7 stop kullanın
- Duygusal kararlar vermeyin
- Stop tetiklenirse çıkın

### 2. Pozisyon Boyutlandırma
- Risk sermayenizin %1-2'si
- Örnek: $10,000 sermaye → $100-200 risk/pozisyon
- Stop mesafesine göre adet hesaplayın

### 3. Piyasa Koşulları
- Boğa piyasasında daha başarılı
- Ayı piyasasında dikkatli olun
- Piyasa trend kontrolü yapın

### 4. Hisse Seçimi
- Yüksek likidite önemli
- Hacim düşük hisselerden kaçının
- Fundamental analiz eklemeniz önerilir

---

## 📈 Performans İpuçları

### Başarı Oranını Artırmak İçin:

1. **Pazar Ortamı Kontrolü**
   - S&P 500 ve XU100 trendini izleyin
   - Boğa piyasasında daha agresif olun

2. **Çoklu Zaman Dilimleri**
   - Günlük grafikle VCP onaylayın
   - Haftalık grafik ana trendi gösterir

3. **Hacim Profili**
   - Breakout anında hacim ÇOK önemli
   - Düşük hacimli breakout'lar riskli

4. **Sabır**
   - Her gün alım yapmak zorunda değilsiniz
   - En iyi setupları bekleyin

---

## 🆘 Sorun Giderme

### "Yeterli veri yok" hatası
- Bazı hisseler için normal
- 200+ günlük veri gerekir
- Yeni listenen hisseler uygun değil

### Telegram mesajı gelmiyor
- Token ve Chat ID'yi kontrol edin
- Bot ile en az bir mesaj gönderin
- İnternet bağlantısını kontrol edin

### Tarama çok yavaş
- Normal: 5-10 dakika sürebilir
- İnternet hızınıza bağlı
- Hisse listesini azaltabilirsiniz

### BIST hisseleri bulunamıyor
- Yahoo Finance'ta BIST sembolü: HISSE.IS
- Örnek: GARAN.IS, AKBNK.IS
- Bazı hisseler Yahoo'da olmayabilir

---

## 📚 Ek Kaynaklar

### Mark Minervini Metodolojisi:
1. "Trade Like a Stock Market Wizard"
2. "Think & Trade Like a Champion"
3. "Momentum Masters"

### Online Kaynaklar:
- Minervini Private Access (website)
- @markminervini Twitter
- YouTube: Mark Minervini interviews

---

## ✅ Hızlı Kontrol Listesi

- [ ] Python ve gerekli kütüphaneler yüklü
- [ ] `universal_scanner.py` çalıştırıldı
- [ ] Watchlist oluşturuldu
- [ ] Telegram bot kuruldu
- [ ] `breakout_config.json` düzenlendi
- [ ] `breakout_alert.py` test edildi
- [ ] Sürekli izleme başlatıldı
- [ ] Mobil bildirimler aktif
- [ ] Stop-loss stratejisi belirlendi

---

## 🎉 Sistem Hazır!

Artık BIST ve ABD borsalarında profesyonel seviyede hisse taraması ve breakout takibi yapabilirsiniz!

**Önemli:** Bu sistem analiz aracıdır, yatırım tavsiyesi değildir. Kendi araştırmanızı yapın ve risk yönetimine dikkat edin.

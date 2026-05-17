# SEPA Metodolojisi - Profesyonel Algoritmik Sinyal Sistemi

## 🎯 Genel Bakış

Mark Minervini'nin **SEPA (Specific Entry Point Analysis)** metodolojisine dayalı, BIST ve ABD piyasalarını tarayan ve JSON formatında sinyal üreten profesyonel algoritmik işlem sistemi.

---

## 📦 Sistem Bileşenleri

### 1. **`sepa_scanner.py`** - Trend Template 2.0 Tarayıcı
- ✅ BIST ve ABD piyasalarını tarar
- ✅ IBD RS > 85 filtresi (ABD)
- ✅ XU100 pozitif ayrışma > 1.2 (BIST)
- ✅ VCP Base tespiti (%25-30 pullback)
- ✅ TL/USD cross-check (BIST için)
- ✅ JSON formatında çıktı

### 2. **`sepa_signal_engine.py`** - Otomatik Sinyal Motoru
- ✅ BUY_SIGNAL üretimi (pivot kırılımı + hacim)
- ✅ SELL_WARNING üretimi (stop, teknik failure)
- ✅ Profit Protection (%15 → breakeven)
- ✅ Telegram webhook entegrasyonu
- ✅ Piyasa saatleri optimizasyonu

---

## 🔧 Kurulum

### Adım 1: SEPA Scanner Çalıştır

```bash
python3 sepa_scanner.py
```

**Ne yapar?**
- BIST ve ABD'den seçili hisseleri tarar
- Trend Template 2.0 kriterlerini uygular
- JSON formatında sonuç üretir

**Çıktı:**
```json
{
  "ticker": "NVDA",
  "market": "US",
  "status": "BREAKOUT",
  "pivot_price": 187.50,
  "stop_loss": 174.30,
  "rs_rank": 92.15
}
```

### Adım 2: Sinyal Motorunu Kur

```bash
python3 sepa_signal_engine.py
```

**İlk çalıştırmada:**
- `sepa_config.json` oluşturulur
- Telegram bilgilerini girin
- Webhook URL ekleyin (opsiyonel)

---

## 📊 Teknik Tarama Parametreleri

### Trend Template 2.0 Kriterleri:

#### 1. **Temel Filtre**
```
✅ Fiyat > 150 günlük SMA
✅ Fiyat > 200 günlük SMA
✅ 200G SMA en az 1 aydır pozitif eğimli
```

#### 2. **Relative Strength (RS)**

**ABD:**
```python
IBD Relative Strength Index > 85
# Ağırlıklandırma:
# - Son 3 ay: %40
# - 3-6 ay: %40
# - 6-9 ay: %20
```

**BIST:**
```python
Sembol/XU100 korelasyonu > 1.2
# Son 3 aydaki pozitif ayrışma
```

#### 3. **VCP (Volatility Contraction Pattern)**
```
Base Yapısı:
- Son 3 ayın en yüksek seviyesinden %25-30 içeride
- Volatilite daralması: %20 → %10 → %3
- Hacim azalması (soldan sağa)
- Son hafta %3'ün altında (Tight)
```

#### 4. **BIST Özel: TL/USD Cross-Check**
```
Her iki grafikte de Aşama 2 onayı:
✅ TL bazlı grafik → Aşama 2
✅ USD bazlı grafik → Aşama 2
```

---

## 🎯 Sinyal ve Otomasyon Mantığı

### 1. Giriş Sinyali (BUY_SIGNAL)

**Koşullar:**
```python
if (fiyat > pivot) and (hacim >= 1.5x ortalama):
    üret("BUY_SIGNAL")
```

**JSON Çıktısı:**
```json
{
  "signal_type": "BUY_SIGNAL",
  "ticker": "NVDA",
  "market": "US",
  "entry_price": 188.50,
  "pivot_price": 187.50,
  "stop_loss": 175.30,
  "volume_ratio": 2.3,
  "rs_rank": 92.15,
  "vcp_confirmed": true,
  "timestamp": "2026-02-17T22:30:15"
}
```

**Telegram Mesajı:**
```
💰 BUY_SIGNAL

MINERVINI BUY ALERT

🇺🇸 US - NVDA

✅ Pivot Kırıldı! (Hacimli)
Giriş: $188.50
Pivot: $187.50
Hacim: 2.3x
RS Rank: 92.15

📊 POZİSYON BİLGİLERİ:
Stop-Loss: $175.30 (-7%)
Hedef 1: $216.78 (+15%)

⚠️ VCP Confirmed: ✅
⏰ 22:30:15
```

---

### 2. Satış Sinyalleri (SELL_WARNING)

#### A. Hard Stop (%7 Zarar)
```python
if fiyat <= entry_price * 0.93:
    üret("SELL_WARNING", reason="HARD_STOP")
```

#### B. Profit Protection (%15 Kâr)
```python
if profit >= 15%:
    stop_loss = entry_price  # Başabaş
    notify("Stop seviyesi başabaş noktasına çekildi")
```

#### C. Technical Failure
```python
if (fiyat < SMA_50) and (hacim > 1.3x):
    üret("SELL_WARNING", reason="TECHNICAL_FAILURE")
```

#### D. High Volume Reversal
```python
if (düşüş > 3%) and (hacim > 1.5x):
    üret("SELL_WARNING", reason="HIGH_VOLUME_REVERSAL")
```

**JSON Çıktısı:**
```json
{
  "signal_type": "SELL_WARNING",
  "sell_reason": "HARD_STOP",
  "ticker": "NVDA",
  "market": "US",
  "current_price": 175.20,
  "entry_price": 188.50,
  "profit_loss_pct": -7.05,
  "reason": "Fiyat stop-loss seviyesine ulaştı (-7%)",
  "timestamp": "2026-02-17T23:15:42"
}
```

---

## ⚙️ Konfigürasyon

### `sepa_config.json`

```json
{
  "telegram_enabled": true,
  "telegram_bot_token": "123456:ABCdef...",
  "telegram_chat_id": "987654321",
  "webhook_url": "https://your-webhook.com/api/signals",
  "hard_stop_pct": 7.0,
  "profit_target_pct": 15.0,
  "volume_spike_threshold": 1.5,
  "check_interval_minutes": 5,
  "market_hours": {
    "us_open": "09:30",
    "us_close": "16:00",
    "bist_open": "10:00",
    "bist_close": "18:00"
  }
}
```

**Parametre Açıklamaları:**

| Parametre | Açıklama | Varsayılan |
|-----------|----------|------------|
| `hard_stop_pct` | Stop-loss yüzdesi | 7.0% |
| `profit_target_pct` | Breakeven için hedef kâr | 15.0% |
| `volume_spike_threshold` | Alım için minimum hacim çarpanı | 1.5x |
| `check_interval_minutes` | İzleme aralığı | 5 dk |

---

## 📈 Piyasa Saatleri Optimizasyonu

### Optimal Tarama Zamanları:

**ABD:**
- 🕘 **09:30 - 10:00** (Açılış ilk 30 dk)
- 🕞 **15:30 - 16:00** (Kapanış son 30 dk)

**BIST:**
- 🕙 **10:00 - 10:30** (Açılış ilk 30 dk)
- 🕞 **17:30 - 18:00** (Kapanış son 30 dk)

**Neden?**
- En yüksek likidite ve hacim
- Kurumsal alımlar daha belirgin
- Breakout'lar daha güvenilir

```python
def is_optimal_scan_time():
    # Sistem otomatik olarak optimal zamanları kontrol eder
    # Bu saatlerde daha aktif tarama yapar
    pass
```

---

## 🚀 Kullanım Senaryoları

### Senaryo 1: Günlük Tarama + Manuel Kontrol

```bash
# Sabah 09:30'da
python3 sepa_scanner.py

# Sonuçları incele
cat sepa_scan_20260217_093000.json

# Sinyalleri kontrol et
python3 sepa_signal_engine.py
# Seçenek 1: Tek kontrol
```

### Senaryo 2: Tam Otomatik İzleme

```bash
# Arka planda çalıştır
nohup python3 sepa_signal_engine.py > sepa_engine.log 2>&1 &

# Mod seçerken: 2 (Sürekli izleme)
# Her 5 dakikada:
# - Tarama sonuçlarını kontrol eder
# - BUY_SIGNAL üretir
# - Aktif pozisyonları izler
# - SELL_WARNING gönderir
```

### Senaryo 3: Webhook Entegrasyonu

```python
# sepa_config.json
{
  "webhook_url": "https://your-trading-bot.com/api/signals",
  ...
}

# Her sinyal otomatik olarak webhook'a POST edilir
# Trading bot sinyalleri işleyip otomatik işlem yapabilir
```

---

## 📊 JSON Şema Detayları

### BUY_SIGNAL Şeması

```json
{
  "signal_type": "BUY_SIGNAL",       // Sabit
  "ticker": "string",                // Hisse kodu
  "market": "US|BIST",               // Piyasa
  "entry_price": float,              // Giriş fiyatı
  "pivot_price": float,              // Pivot seviyesi
  "stop_loss": float,                // Stop-loss
  "volume_ratio": float,             // Hacim çarpanı
  "rs_rank": float,                  // RS puanı
  "timestamp": "ISO-8601",           // Zaman damgası
  "vcp_confirmed": boolean           // VCP onayı
}
```

### SELL_WARNING Şeması

```json
{
  "signal_type": "SELL_WARNING",                    // Sabit
  "sell_reason": "HARD_STOP|TECHNICAL_FAILURE|...", // Sebep
  "ticker": "string",                               // Hisse kodu
  "market": "US|BIST",                              // Piyasa
  "current_price": float,                           // Mevcut fiyat
  "entry_price": float,                             // Giriş fiyatı
  "profit_loss_pct": float,                         // Kâr/Zarar %
  "reason": "string",                               // Açıklama
  "timestamp": "ISO-8601"                           // Zaman damgası
}
```

---

## 🔄 Workflow Diyagramı

```
┌─────────────────────────────────────────────────────────────────┐
│                     SEPA SİSTEMİ WORKFLOW                       │
└─────────────────────────────────────────────────────────────────┘

1. TARAMA AŞAMASI
   │
   ├─► sepa_scanner.py çalıştır
   │   │
   │   ├─► ABD Hisseleri Tara (RS > 85)
   │   │   └─► VCP Base Tespit Et
   │   │
   │   ├─► BIST Hisseleri Tara (TL/USD Cross-Check)
   │   │   └─► VCP Base Tespit Et
   │   │
   │   └─► JSON Sonuç Üret
   │       └─► sepa_scan_TIMESTAMP.json
   │
2. SİNYAL ÜRETME
   │
   ├─► sepa_signal_engine.py başlat
   │   │
   │   ├─► Tarama Sonuçlarını Yükle
   │   │
   │   ├─► Her 5 Dakikada:
   │   │   │
   │   │   ├─► BREAKOUT/PIVOT_TOUCH Kontrol Et
   │   │   │   └─► Hacim > 1.5x ise → BUY_SIGNAL
   │   │   │       └─► Telegram + Webhook
   │   │   │
   │   │   ├─► Aktif Pozisyonları İzle
   │   │   │   │
   │   │   │   ├─► Hard Stop (-7%) → SELL_WARNING
   │   │   │   ├─► Profit Target (+15%) → Move Stop to Breakeven
   │   │   │   ├─► Technical Failure → SELL_WARNING
   │   │   │   └─► Volume Reversal → SELL_WARNING
   │   │   │
   │   │   └─► Sinyal Geçmişini Kaydet
   │   │
   │   └─► Optimal Zamanlarda Daha Aktif
   │
3. SONUÇ
   │
   ├─► sepa_signal_history.json (Tüm sinyaller)
   ├─► Telegram Bildirimleri (Real-time)
   └─► Webhook POST (Otomasyon için)
```

---

## 💡 Gelişmiş Özellikler

### 1. Cross-Market Analiz
```python
# BIST hissesi hem TL hem USD grafikte Aşama 2'de mi?
if tl_stage2 and usd_stage2:
    # Sadece çift onaylılar geçer
    pass
```

### 2. IBD Tarzı RS Hesaplama
```python
# Ağırlıklandırılmış performans
rs_score = (q1_perf * 0.40) + (q2_perf * 0.40) + (q3_perf * 0.20)
# 0-99 skalasında normalize edilmiş
```

### 3. VCP Base Tespiti
```python
# Otomatik volatilite daralması tespiti
contractions = detect_contracting_volatility(weeks)
is_tight = last_week_volatility < 3.0
volume_decreasing = check_volume_trend(weeks)
```

### 4. Dinamik Stop Yönetimi
```python
# %15 kâra ulaşınca otomatik breakeven
if profit >= 15%:
    stop = entry_price
    notify("Risk eliminate edildi")
```

---

## 📁 Dosya Yapısı

```
MARK MİNERVİNİ/
├── sepa_scanner.py              # Ana tarayıcı
├── sepa_signal_engine.py        # Sinyal motoru
├── sepa_config.json             # Konfigürasyon
├── sepa_scan_*.json             # Tarama sonuçları
└── sepa_signal_history.json     # Sinyal geçmişi
```

---

## ⚠️ Önemli Notlar

### 1. Gerçek Parayla İşlem
- Bu sistem analiz aracıdır, otomatik işlem yapmaz
- Sinyalleri manuel onaylayın
- Risk yönetimi kurallarına uyun

### 2. Backtesting
- Geçmiş verilerde test edin
- Parametre optimizasyonu yapın
- Paper trading ile doğrulayın

### 3. API Limitleri
- Yahoo Finance ücretsiz sınırları var
- Çok sık tarama yapmayın
- Gerekirse premium API kullanın

### 4. Webhook Güvenliği
- HTTPS kullanın
- API key ile kimlik doğrulama
- Rate limiting uygulayın

---

## 🎓 SEPA Metodolojisi Referansları

### Mark Minervini Kaynakları:
1. **"Trade Like a Stock Market Wizard"**
   - Specific Entry Point Analysis (SEPA)
   - Trend Template açıklaması

2. **"Think & Trade Like a Champion"**
   - VCP pattern detayları
   - RS ranking sistemi

3. **Minervini Private Access**
   - IBD RS kullanımı
   - Position management

---

## ✅ Hızlı Başlangıç Kontrol Listesi

- [ ] `sepa_scanner.py` test edildi
- [ ] `sepa_config.json` düzenlendi
- [ ] Telegram bot bağlandı
- [ ] İlk tarama yapıldı
- [ ] JSON çıktısı doğrulandı
- [ ] Signal engine test edildi
- [ ] Webhook entegrasyonu (opsiyonel)
- [ ] Sürekli izleme başlatıldı

---

## 🎯 Sonuç

SEPA sistemi ile artık:
- ✅ Profesyonel seviyede algoritmik tarama
- ✅ JSON formatında entegre edilebilir sinyaller
- ✅ Otomatik risk yönetimi
- ✅ Real-time Telegram/webhook bildirimleri
- ✅ BIST ve ABD piyasaları tek sistemde

**Başarılı işlemler! 📈**

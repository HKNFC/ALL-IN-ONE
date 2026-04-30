# CHECKPOINT — SEPA Stock Scanner v1.0
**Tarih:** 25 Şubat 2026  
**Durum:** Stabil, tüm özellikler çalışıyor

---

## Bu Checkpoint'te Neler Var?

| Özellik | Durum |
|---------|-------|
| BIST & USA Tarama (Stock Scanner) | ✅ |
| Backtest (RS + Minervini metodolojisi) | ✅ |
| Portföy Yönetimi | ✅ |
| Piyasa Durumu Paneli (VIX dahil) | ✅ |
| Disk Cache (Deterministik backtest) | ✅ |
| Duplicate Backtest Önleme | ✅ |
| NaN → null JSON sanitizasyonu | ✅ |
| Güncel fiyat (USA portföyleri) | ✅ |
| About sayfası | ✅ |

---

## KRİTİK — DEĞİŞTİRİLMEMESİ GEREKEN KURALLAR

### 1. RS (Relative Strength) Formülü
**Dosya:** `universal_scanner.py` → `calculate_rs_us()` ve `calculate_rs_bist()`  
**Dosya:** `backtest_engine.py` → `select_top_stocks()`

```
⚠️ RS değerine ASLA min/max cap (örn. min(100, max(0, rs))) EKLEME!
```

RS ham bağıl getiri değeri olarak korunmalı (MU=316, CIEN=167, FIX=134 gibi).  
Cap eklenirse tüm güçlü hisseler aynı skoru alır → sıralama rastgeleleşir → backtest ve scanner farklı sonuç verir.

### 2. Disk Cache Mantığı
**Dosya:** `app.py` → `MarketDataCache` sınıfı  
**Klasör:** `data_cache/*.pkl`

- yfinance her çağrıda adjusted close fiyatları biraz değiştirebilir.
- Disk cache sayesinde aynı parametreli backtest her zaman aynı sonucu verir.
- TTL = 1 gün (ertesi gün taze veri çeker).
- 30 günden eski dosyalar sunucu başlangıcında otomatik silinir.

**Cache'i ASLA devre dışı bırakma** — bırakırsan aynı gün aynı saatte farklı backtest sonuçları üretilir.

### 3. Backtest Duplicate Önleme
**Dosya:** `app.py` → `/api/backtest/run` endpoint'i

Aynı parametrelerle (market + method + start_date + end_date + frequency + capital) tekrar backtest çalıştırıldığında:
- Yeni hesaplama yapılmaz
- Disk'teki kayıtlı sonuç döndürülür

Bu davranışı değiştirme — kullanıcının "neden aynı sonuç çıkmıyor?" sorusunu önler.

### 4. Scanner ve Backtest Aynı Mantığı Kullanmalı
**Dosya:** `universal_scanner.py` ve `backtest_engine.py`

Scanner (Stock Scanner sayfası) ve Backtest aynı filtreleme/RS hesaplama mantığını kullanır.  
Birini değiştirirsen diğerini de değiştir — yoksa aynı gün farklı hisseler seçilir.

### 5. Cache Versiyon Kontrolü
**Dosya:** `static/js/app.js` → `CACHE_VERSION = 'v3-rs-fixed'`

Büyük bir değişiklik yapıldığında bu versiyonu artır (örn. `v4-...`).  
Bu sayede eski tarayıcı cache'leri otomatik temizlenir.

---

## Test Komutları

```bash
# Temel bütünlük testi
cd "/Users/hakanficicilar/Documents/Aİ/MARK MİNERVİNİ"
python3 scan_integrity_test.py

# Uygulamayı başlat
python3 app.py

# URL
# http://localhost:5555
```

---

## Önemli Dosyalar

| Dosya | Açıklama |
|-------|----------|
| `app.py` | Ana Flask uygulaması, tüm API endpoint'leri |
| `backtest_engine.py` | Backtest mantığı, RS tabanlı hisse seçimi |
| `universal_scanner.py` | BIST ve USA tarama motoru |
| `scan_integrity_test.py` | Bütünlük ve determinizm testleri |
| `data_cache/` | Disk cache klasörü (otomatik yönetilir) |
| `backtests/` | Kaydedilmiş backtest sonuçları (JSON) |
| `portfolios/` | Portföy verileri |

---

## Bilinen Sınırlamalar

- Yahoo Finance bazen bazı hisseler için "no price data found" verir — bu normal, sistem atlar.
- BIST'te 596 hisse arasından yaklaşık 365-400'ü için yeterli veri indirilebilir (geri kalanlar listelerde yok veya veri yetersiz).
- Twelvedata Growth Plan: 1.5M kredi/ay — `batch_size=55` ile optimize edilmiş.

---

*Bu checkpoint git commit olarak da kaydedilmiştir.*

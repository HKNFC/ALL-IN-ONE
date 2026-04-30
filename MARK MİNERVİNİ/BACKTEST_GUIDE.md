# ⏮️ Backtest Sistemi - Kullanım Kılavuzu

## 🎯 Nedir?

**Minervini Backtest Engine**, geçmiş tarihlerde Mark Minervini stratejisini uygulayarak portföy performansını test eden otomatik bir sistemdir.

---

## 🔧 Nasıl Çalışır?

### 1️⃣ **Aylık Rebalancing**
- **Her ayın ilk işlem günü** sonunda tarama yapılır
- Pazar kapalıysa bir sonraki işlem günü kullanılır
- Otomatik tatil kontrolü

### 2️⃣ **Hisse Seçimi**
**Filtreleme:**
1. BREAKOUT ve PIVOT_NEAR statusündeki hisseler seçilir
2. RS skoruna göre yüksekten düşüğe sıralanır
3. Top 5 hisse portföye alınır

**Sıralama Kriteri:**
- **US:** IBD Relative Strength (RS)
- **BIST:** XU100'e göre RS Divergence %

### 3️⃣ **Portföy Yönetimi**
**Alım:**
- Her hisse için eşit ağırlık (sermayenin 1/5'i)
- Aylık rebalancing'de eski pozisyonlar kapatılır
- Yeni top 5 hisse alınır

**Satım:**
- Bir ay sonraki rebalancing'de otomatik sat
- Kar/zarar hesaplanır
- Sermaye güncellenir

### 4️⃣ **Performans Metrikleri**
Sistem otomatik olarak hesaplar:
- **Total Return %**: Toplam getiri
- **Sharpe Ratio**: Risk-adjusted return
- **Max Drawdown**: En büyük düşüş
- **Win Rate**: Kazanan işlem yüzdesi
- **Average Win/Loss**: Ortalama kazanç/kayıp

---

## 🚀 Kullanım Adımları

### Web Arayüzü:

1. **Backtest sayfasına git:**
   ```
   http://localhost:8888/backtest
   ```

2. **Parametreleri ayarla:**
   - **Başlangıç Tarihi**: Örn: 2023-01-01
   - **Bitiş Tarihi**: Örn: 2024-12-31
   - **Market**: US, BIST veya Both
   - **Başlangıç Sermayesi**: Örn: $100,000

3. **"🚀 Backtest Başlat"** butonuna tıkla

4. **Sonuçları incele:**
   - Metrikler (6 adet kart)
   - Equity Curve grafiği
   - Detaylı işlem geçmişi

---

## 📊 Sonuç Ekranı

### A) **Metrik Kartları:**

```
┌─────────────────────────────────────────────────────────────┐
│ 💰 Final Değer        │ 📈 Toplam Getiri                    │
│ $125,450              │ +25.45%                             │
├─────────────────────────────────────────────────────────────┤
│ 📉 Max Drawdown       │ 🎯 Win Rate                         │
│ -8.5%                 │ 65%                                 │
├─────────────────────────────────────────────────────────────┤
│ 📊 Sharpe Ratio       │ 🔄 Toplam İşlem                     │
│ 1.8                   │ 120                                 │
└─────────────────────────────────────────────────────────────┘
```

### B) **Equity Curve:**
- X-axis: Tarih
- Y-axis: Portfolio değeri ($)
- Chart.js ile interaktif grafik

### C) **İşlem Geçmişi Tablosu:**
- Tarih, Aksiyon (BUY/SELL), Ticker
- Miktar, Fiyat, Toplam Değer
- Kar/Zarar ($), Kar/Zarar (%)

---

## 🧪 Örnek Senaryo

### Parametre:
```
Başlangıç: 2023-01-01
Bitiş: 2024-12-31
Market: US
Sermaye: $100,000
```

### İlk Rebalancing (2023-01-02):

**Tarama Sonucu:** 15 BREAKOUT/PIVOT_NEAR hisse bulundu

**Top 5 (RS Sıralı):**
1. NVDA - RS: 95 - BREAKOUT
2. META - RS: 92 - BREAKOUT
3. AAPL - RS: 88 - PIVOT_NEAR
4. MSFT - RS: 85 - BREAKOUT
5. GOOGL - RS: 82 - PIVOT_NEAR

**Alım:**
- Her hisse için $20,000 (100K / 5)
- NVDA: 50 adet @ $400
- META: 70 adet @ $286
- AAPL: 120 adet @ $167
- MSFT: 80 adet @ $250
- GOOGL: 200 adet @ $100

### İkinci Rebalancing (2023-02-01):

**Mevcut Portföy Sat:**
- NVDA: 50 @ $450 → +$2,500
- META: 70 @ $310 → +$1,680
- AAPL: 120 @ $175 → +$960
- MSFT: 80 @ $260 → +$800
- GOOGL: 200 @ $105 → +$1,000

**Toplam:** $106,940 (6.94% kazanç 1 ayda)

**Yeni Top 5 Al:**
- TSLA, AMD, NFLX, AMZN, COST (yeni seçim)

...ve böyle devam eder.

---

## 📈 Performans Yorumlama

### **Total Return:**
- **0-10%**: Düşük performans
- **10-20%**: Orta performans
- **20%+**: Yüksek performans
- **Karşılaştırma**: S&P 500 getirisi ile karşılaştır

### **Sharpe Ratio:**
- **< 1**: Zayıf risk-adjusted return
- **1-2**: İyi
- **2+**: Mükemmel

### **Max Drawdown:**
- **0-10%**: Düşük risk
- **10-20%**: Orta risk
- **20%+**: Yüksek risk

### **Win Rate:**
- **< 50%**: Strateji zayıf
- **50-60%**: Orta
- **60%+**: Güçlü strateji

---

## ⚠️ Önemli Notlar

### 1️⃣ **Geçmiş Performans ≠ Gelecek Sonuç**
Backtest sonuçları sadece tarihsel verilere dayalıdır. Gelecek performansı garanti etmez.

### 2️⃣ **Slippage ve Komisyon Dahil Değil**
- İşlem komisyonları göz ardı edilmiştir
- Slippage (alış/satışta kayma) hesaplanmamıştır
- Gerçek dünyada getiri %1-2 daha düşük olabilir

### 3️⃣ **Survivorship Bias**
Sistemde sadece şu anda var olan hisseler taranır. İflas eden şirketler dahil değil.

### 4️⃣ **İlk 30 Hisse Sınırı**
Performans için her market'ten ilk 30 hisse taranır (full scan çok yavaş).

### 5️⃣ **Data Quality**
Yahoo Finance API kullanılır. Veri eksikliği/hatası olabilir.

---

## 🛠️ Teknik Detaylar

### Backend: `backtest_engine.py`

**Sınıf:** `MinerviniBacktest`

**Ana Metodlar:**
```python
__init__(start_date, end_date, initial_capital)
get_monthly_rebalance_dates()
scan_market_at_date(scan_date, market)
select_top_stocks(scan_results, top_n=5)
rebalance_portfolio(new_stocks, current_date)
calculate_portfolio_value(current_date)
run_backtest(market)
generate_report()
```

### API Endpoint:
```
POST /api/backtest

Body:
{
  "start_date": "2023-01-01",
  "end_date": "2024-12-31",
  "market": "US",
  "initial_capital": 100000
}

Response:
{
  "success": true,
  "report": {
    "summary": {...},
    "equity_curve": [...],
    "trade_history": [...]
  }
}
```

### Frontend: `backtest.html`
- Chart.js için equity curve grafiği
- Responsive tasarım
- Real-time progress bar
- Detaylı tablo görünümü

---

## 💡 İpuçları

### 1️⃣ **Farklı Dönemler Test Et**
```
Bull Market: 2020-2021
Bear Market: 2022
Sideways: 2015-2016
```

### 2️⃣ **Market Karşılaştırması**
- US vs BIST ayrı ayrı test et
- Hangi pazar daha iyi performans veriyor?

### 3️⃣ **Sermaye Büyüklüğü**
- $10K, $50K, $100K ile test et
- Küçük sermayede diversifikasyon zorluğu

### 4️⃣ **Top N Sayısını Değiştir**
Backend'de `top_n=5` parametresini değiştir:
```python
top_stocks = self.select_top_stocks(scan_results, top_n=3)  # Top 3
```

---

## 🔄 Gelecek Geliştirmeler

### Planlanan Özellikler:
- [ ] Stop-loss implementasyonu (%7)
- [ ] Trailing stop (dinamik stop)
- [ ] Pozisyon sizing (RS bazlı ağırlık)
- [ ] Komisyon/slippage hesabı
- [ ] Monte Carlo simülasyonu
- [ ] Multiple strategy comparison
- [ ] PDF rapor export
- [ ] Email bildirim (backtest bitince)

---

## 📚 Referanslar

**Mark Minervini Kitapları:**
- "Trade Like a Stock Market Wizard"
- "Think & Trade Like a Champion"

**Backtest Metodolojisi:**
- Walk-forward analysis
- Monthly rebalancing
- Top N momentum selection
- Equal weighting

---

## 🎯 Sonuç

Backtest sistemi, Minervini stratejisinin geçmişte nasıl performans gösterdiğini analiz etmek için güçlü bir araçtır.

**Kullanım:**
1. Farklı dönemleri test edin
2. Sonuçları analiz edin
3. Stratejiyi optimize edin
4. **Ama unutmayın:** Geçmiş performans gelecek garantisi değildir!

**Not:** Bu bir eğitim aracıdır. Gerçek yatırım kararları için profesyonel danışmanlık alın.

# Mark Minervini Portföy İzleme Sistemi - Kurulum ve Kullanım Kılavuzu

## 📋 Genel Bakış

Bu sistem, Mark Minervini'nin risk yönetimi kurallarına göre portföyünüzü 7/24 izler ve kritik durumlarda Telegram üzerinden anında uyarı gönderir.

## 🚨 İzlenen Kurallar

### 1. **Hard Stop (%7 Zarar Limiti)**
- Fiyat, alım maliyetinizin %7 altına düşerse
- **Mesaj:** "ACİL SAT: Stop Limitine Ulaşıldı"
- **Öncelik:** 🚨 KRİTİK

### 2. **Backstop (Kâr Koruma)**
- Hisse %15 kâra ulaştığında stop seviyesi otomatik olarak başabaş noktasına çekilir
- **Mesaj:** "Backstop Aktif: Kâr Koruması"
- **Öncelik:** ℹ️ BİLGİ

### 3. **Teknik Satış Sinyali**
- Fiyat 50 günlük SMA'nın altında hacimli kapanış yaparsa
- **Mesaj:** "ZAYIFLIK SİNYALİ: 50 Günlük Ortalama Kırıldı"
- **Öncelik:** ⚠️ UYARI

### 4. **Hacimli Ters Dönüş**
- Fiyat %3'ten fazla düşerken hacim son 10 günün ortalamasının üzerindeyse
- **Mesaj:** "Hacimli Ters Dönüş Uyarısı"
- **Öncelik:** ⚠️ UYARI

---

## 🛠 Kurulum Adımları

### Adım 1: Telegram Bot Oluşturma

1. **Telegram'da @BotFather'ı açın**
   - Telegram uygulamasında @BotFather aratın
   - `/start` komutunu gönderin

2. **Yeni bot oluşturun**
   ```
   /newbot
   ```
   - Bot için bir isim girin (örnek: "Portföy İzleyici")
   - Bot için kullanıcı adı girin (örnek: "my_portfolio_bot")
   - Bot Token'ınızı kopyalayın (örnek: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

3. **Chat ID'nizi öğrenin**
   - @userinfobot'u açın
   - Chat ID'nizi kopyalayın (örnek: `987654321`)

### Adım 2: Konfigürasyon Dosyasını Düzenleme

`telegram_config.json` dosyasını açın ve Bot Token ile Chat ID'nizi girin:

```json
{
  "telegram_bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
  "telegram_chat_id": "987654321",
  "hard_stop_pct": 7.0,
  "profit_target_for_backstop": 15.0,
  "sma_period": 50,
  "price_drop_threshold_pct": 3.0,
  "volume_multiplier": 1.0,
  "alert_cooldown_minutes": 60,
  "monitoring_interval_minutes": 15
}
```

**Parametre Açıklamaları:**
- `hard_stop_pct`: Zarar durdurma yüzdesi (varsayılan: 7%)
- `profit_target_for_backstop`: Backstop için hedef kâr (varsayılan: 15%)
- `sma_period`: Hareketli ortalama periyodu (varsayılan: 50 gün)
- `price_drop_threshold_pct`: Ters dönüş için fiyat düşüş eşiği (varsayılan: 3%)
- `volume_multiplier`: Hacim çarpanı (varsayılan: 1.0x)
- `alert_cooldown_minutes`: Aynı uyarı için bekleme süresi (varsayılan: 60 dk)
- `monitoring_interval_minutes`: İzleme aralığı (varsayılan: 15 dk)

### Adım 3: Portföy Dosyasını Düzenleme

`my_portfolio.csv` dosyasını açın ve kendi hisselerinizi ekleyin:

**Örnek Portföy:**
```csv
Ticker,Maliyet,Adet,Alış_Tarihi,Stop_Seviyesi,Backstop_Aktif
AAPL,150.00,10,2024-01-15,139.50,False
NVDA,200.00,5,2024-02-01,186.00,False
GOOGL,280.00,8,2024-02-10,260.40,False
RTX,200.00,15,2024-02-15,186.00,False
LMT,650.00,3,2024-02-16,604.50,False
```

**Sütun Açıklamaları:**
- `Ticker`: Hisse sembolü (örnek: AAPL, NVDA)
- `Maliyet`: Ortalama alış fiyatı (USD)
- `Adet`: Sahip olunan hisse sayısı
- `Alış_Tarihi`: İlk alım tarihi (YYYY-MM-DD formatında)
- `Stop_Seviyesi`: Manuel belirlediğiniz stop seviyesi (varsayılan: maliyet * 0.93)
- `Backstop_Aktif`: Backstop aktif mi? (False/True) - sistem otomatik güncelleyecek

---

## 🚀 Sistemi Çalıştırma

### Mod 1: Tek Kontrol (Test için)

```bash
python3 portfolio_monitor.py
```

Açılan menüden **1** seçin.

- Tüm hisselerinizi bir kez kontrol eder
- Telegram'a test mesajı gönderir
- Sonuçları ekrana yazdırır

### Mod 2: Sürekli İzleme (7/24 Aktif)

```bash
python3 portfolio_monitor.py
```

Açılan menüden **2** seçin.

- Her 15 dakikada bir portföyünüzü kontrol eder
- Uyarıları otomatik olarak Telegram'a gönderir
- Durdurmak için `Ctrl+C` basın

### Arka Planda Çalıştırma (Önerilen)

**macOS/Linux:**
```bash
nohup python3 portfolio_monitor.py > monitor.log 2>&1 &
```

**Windows:**
```bash
pythonw portfolio_monitor.py
```

---

## 📱 Telegram Mesaj Örnekleri

### 🚨 ACİL SAT Mesajı
```
🚨 ACİL 🚨

ACİL SAT: Stop Limitine Ulaşıldı

Hisse: AAPL
Mevcut Fiyat: $139.50
Maliyet: $150.00
Stop Seviyesi: $139.50
Zarar: -7.00%

⚠️ Derhal satış yapmanız önerilir!
```

### ℹ️ Backstop Aktif Mesajı
```
ℹ️ BİLGİ

Backstop Aktif: Kâr Koruması

Hisse: NVDA
Mevcut Fiyat: $230.00
Maliyet: $200.00
Kâr: +15.00%

Stop seviyesi başabaş noktasına çekildi:
Yeni Stop: $200.00

✅ Artık minimum riskte kâr takibi yapıyorsunuz!
```

### ⚠️ SMA Kırılımı Mesajı
```
⚠️ UYARI

ZAYIFLIK SİNYALİ: 50 Günlük Ortalama Kırıldı

Hisse: GOOGL
Mevcut Fiyat: $275.00
50-Günlük SMA: $280.50
Hacim Oranı: 1.8x

⚠️ Teknik destek kırıldı, pozisyon gözden geçirilmeli!
```

---

## 🔧 Sorun Giderme

### "Telegram bağlantısı başarısız!"

**Çözüm:**
1. `telegram_config.json` dosyasında Bot Token ve Chat ID'nin doğru olduğundan emin olun
2. Bot ile en az bir mesaj göndermiş olduğunuzdan emin olun (botunuzu açıp `/start` yazın)
3. İnternet bağlantınızı kontrol edin

### "Portföy boş, izlenecek hisse yok"

**Çözüm:**
1. `my_portfolio.csv` dosyasının mevcut olduğundan emin olun
2. Dosyada en az bir hisse bulunduğundan emin olun
3. CSV formatının doğru olduğunu kontrol edin

### "Yeterli veri yok" Uyarısı

**Çözüm:**
- Bazı hisseler için yeterli geçmiş veri olmayabilir
- Yeni listelenmiş hisseler için normal bir durumdur
- Hisse sembolünün doğru olduğundan emin olun

---

## 📊 İleri Seviye Özelleştirme

### Parametreleri Değiştirme

`telegram_config.json` dosyasında istediğiniz parametreyi değiştirebilirsiniz:

**Daha sıkı stop (%5):**
```json
"hard_stop_pct": 5.0
```

**Backstop'u %20 kârda aktifleştir:**
```json
"profit_target_for_backstop": 20.0
```

**Her 5 dakikada kontrol et:**
```json
"monitoring_interval_minutes": 5
```

### Uyarı Cooldown'ı Ayarlama

Aynı uyarının çok sık gönderilmesini engellemek için:
```json
"alert_cooldown_minutes": 120
```
(120 dakika = 2 saat)

---

## 📈 Kullanım Senaryoları

### Senaryo 1: İş Günü İzleme
```bash
# Sabah piyasa açılışında başlat
python3 portfolio_monitor.py
# 2. Sürekli izleme seç
# Akşam piyasa kapanışında Ctrl+C ile durdur
```

### Senaryo 2: 7/24 İzleme
```bash
# Arka planda sürekli çalıştır
nohup python3 portfolio_monitor.py > monitor.log 2>&1 &

# Logları kontrol et
tail -f monitor.log
```

### Senaryo 3: Önemli Günlerde (Earnings vb.)
```json
// telegram_config.json
"monitoring_interval_minutes": 5,  // Her 5 dakikada kontrol
"alert_cooldown_minutes": 15      // Daha sık uyarı
```

---

## 🔐 Güvenlik Notları

1. **telegram_config.json dosyasını kimseyle paylaşmayın!**
   - Bot Token'ınız hassas bilgidir
   
2. **GitHub'a yüklerken dikkat edin:**
   ```bash
   # .gitignore dosyasına ekleyin:
   telegram_config.json
   my_portfolio.csv
   ```

3. **Bot Token'ınızı koruyun:**
   - Token sızdıysa @BotFather'dan token'ı yenileyin

---

## 💡 İpuçları

1. **İlk Kurulumda Test Edin:**
   - Önce "Tek Kontrol" moduyla test yapın
   - Telegram mesajlarının geldiğinden emin olun

2. **Portföyü Güncel Tutun:**
   - Yeni alım/satım yaptığınızda `my_portfolio.csv`'yi güncelleyin
   - Stop seviyelerini manuel olarak ayarlayabilirsiniz

3. **Piyasa Saatleri:**
   - Sistem hafta sonları ve piyasa kapalıyken de çalışır
   - Sadece Telegram mesajlarını daha seyrek alırsınız

4. **Mobil Bildirimler:**
   - Telegram mobil uygulamasında bildirimleri açık tutun
   - Önemli uyarıları kaçırmayın

---

## 📞 Destek ve Geliştirme

Bu sistem şu scriptlerle birlikte çalışır:
- `minervini_scanner.py` - Trend Template tarayıcı
- `vcp_scanner.py` - VCP pattern bulucu
- `portfolio_monitor.py` - Portföy izleyici (bu sistem)

**Sonraki Adımlar:**
1. VCP tarayıcısıyla bulduğunuz hisseleri portföye ekleyin
2. Sistemi çalıştırın ve rahat uyuyun
3. Telegram'dan gelen uyarıları takip edin

---

## ✅ Hızlı Başlangıç Kontrol Listesi

- [ ] Telegram bot oluşturuldu
- [ ] Bot Token ve Chat ID alındı
- [ ] `telegram_config.json` düzenlendi
- [ ] `my_portfolio.csv` kendi hisselerle güncellendi
- [ ] Test mesajı başarıyla alındı
- [ ] Sistem sürekli izleme modunda çalışıyor
- [ ] Mobil bildirimler aktif

**Sisteminiz hazır! 🎉**

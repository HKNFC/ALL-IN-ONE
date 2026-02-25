#!/usr/bin/env python3
"""
Mark Minervini Portföy İzleme ve Telegram Uyarı Sistemi
Real-time hisse takibi ve risk yönetimi
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
import os
import requests
import warnings
warnings.filterwarnings('ignore')

class TelegramNotifier:
    """Telegram bot ile bildirim gönderme"""
    
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    def send_message(self, message, priority="normal"):
        """Telegram'a mesaj gönder"""
        try:
            # Önceliğe göre emoji ekle
            if priority == "critical":
                message = f"🚨 ACİL 🚨\n\n{message}"
            elif priority == "warning":
                message = f"⚠️ UYARI\n\n{message}"
            elif priority == "info":
                message = f"ℹ️ BİLGİ\n\n{message}"
            
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(self.api_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                print(f"✓ Telegram mesajı gönderildi: {priority}")
                return True
            else:
                print(f"✗ Telegram hatası: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"✗ Telegram gönderim hatası: {e}")
            return False

class PortfolioMonitor:
    """Portföy izleme ve kural kontrolü"""
    
    def __init__(self, portfolio_file, config_file, telegram_notifier):
        self.portfolio_file = portfolio_file
        self.config_file = config_file
        self.notifier = telegram_notifier
        self.portfolio = self.load_portfolio()
        self.config = self.load_config()
        self.alert_history = {}  # Son uyarı zamanlarını takip et
    
    def load_portfolio(self):
        """Portföy dosyasını yükle"""
        try:
            if os.path.exists(self.portfolio_file):
                df = pd.read_csv(self.portfolio_file)
                print(f"✓ Portföy yüklendi: {len(df)} hisse")
                return df
            else:
                print(f"⚠ Portföy dosyası bulunamadı: {self.portfolio_file}")
                return pd.DataFrame()
        except Exception as e:
            print(f"✗ Portföy yükleme hatası: {e}")
            return pd.DataFrame()
    
    def load_config(self):
        """Konfigürasyon dosyasını yükle"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                print(f"✓ Konfigürasyon yüklendi")
                return config
            else:
                # Varsayılan config
                return {
                    "hard_stop_pct": 7.0,
                    "profit_target_for_backstop": 15.0,
                    "sma_period": 50,
                    "price_drop_threshold_pct": 3.0,
                    "volume_multiplier": 1.0,
                    "alert_cooldown_minutes": 60
                }
        except Exception as e:
            print(f"✗ Config yükleme hatası: {e}")
            return {}
    
    def save_portfolio(self):
        """Portföyü kaydet"""
        try:
            self.portfolio.to_csv(self.portfolio_file, index=False, encoding='utf-8-sig')
            print(f"✓ Portföy güncellendi")
        except Exception as e:
            print(f"✗ Portföy kaydetme hatası: {e}")
    
    def can_send_alert(self, ticker, alert_type):
        """Aynı uyarıyı sık sık göndermemek için cooldown kontrolü"""
        key = f"{ticker}_{alert_type}"
        now = datetime.now()
        
        if key in self.alert_history:
            last_alert = self.alert_history[key]
            cooldown = timedelta(minutes=self.config.get('alert_cooldown_minutes', 60))
            
            if now - last_alert < cooldown:
                return False
        
        self.alert_history[key] = now
        return True
    
    def check_hard_stop(self, ticker, current_price, cost_basis):
        """Hard Stop kontrolü: %7 zarar"""
        stop_price = cost_basis * (1 - self.config['hard_stop_pct'] / 100)
        
        if current_price <= stop_price:
            loss_pct = ((current_price - cost_basis) / cost_basis) * 100
            
            if self.can_send_alert(ticker, 'hard_stop'):
                message = (
                    f"<b>ACİL SAT: Stop Limitine Ulaşıldı</b>\n\n"
                    f"Hisse: <b>{ticker}</b>\n"
                    f"Mevcut Fiyat: <b>${current_price:.2f}</b>\n"
                    f"Maliyet: ${cost_basis:.2f}\n"
                    f"Stop Seviyesi: ${stop_price:.2f}\n"
                    f"Zarar: <b>{loss_pct:.2f}%</b>\n\n"
                    f"⚠️ Derhal satış yapmanız önerilir!"
                )
                self.notifier.send_message(message, priority="critical")
                return True
        
        return False
    
    def check_backstop(self, row, current_price):
        """Backstop: %15 kâr sonrası stop'u başabaşa çek"""
        ticker = row['Ticker']
        cost_basis = row['Maliyet']
        current_stop = row.get('Stop_Seviyesi', cost_basis * 0.93)
        profit_pct = ((current_price - cost_basis) / cost_basis) * 100
        
        # %15 kâra ulaştıysa ve stop henüz başabaşta değilse
        if profit_pct >= self.config['profit_target_for_backstop']:
            if current_stop < cost_basis * 0.99:  # Stop başabaşın altındaysa
                # Stop'u başabaş noktasına çek
                new_stop = cost_basis
                
                # Portföyde güncelle
                idx = self.portfolio[self.portfolio['Ticker'] == ticker].index[0]
                self.portfolio.at[idx, 'Stop_Seviyesi'] = new_stop
                self.portfolio.at[idx, 'Backstop_Aktif'] = True
                self.save_portfolio()
                
                if self.can_send_alert(ticker, 'backstop'):
                    message = (
                        f"<b>Backstop Aktif: Kâr Koruması</b>\n\n"
                        f"Hisse: <b>{ticker}</b>\n"
                        f"Mevcut Fiyat: <b>${current_price:.2f}</b>\n"
                        f"Maliyet: ${cost_basis:.2f}\n"
                        f"Kâr: <b>+{profit_pct:.2f}%</b>\n\n"
                        f"Stop seviyesi başabaş noktasına çekildi:\n"
                        f"Yeni Stop: <b>${new_stop:.2f}</b>\n\n"
                        f"✅ Artık minimum riskte kâr takibi yapıyorsunuz!"
                    )
                    self.notifier.send_message(message, priority="info")
                    return True
        
        return False
    
    def check_sma_break(self, ticker, df, current_price, current_volume):
        """50 günlük SMA kırılımı kontrolü"""
        if len(df) < self.config['sma_period']:
            return False
        
        sma_50 = df['Close'].rolling(window=self.config['sma_period']).mean().iloc[-1]
        prev_close = df['Close'].iloc[-2]
        avg_volume = df['Volume'].tail(20).mean()
        
        # Önceki kapanış SMA üstündeydi, şimdi altında ve hacimli
        if prev_close >= sma_50 and current_price < sma_50:
            volume_ratio = current_volume / avg_volume
            
            if volume_ratio > self.config['volume_multiplier']:
                if self.can_send_alert(ticker, 'sma_break'):
                    message = (
                        f"<b>ZAYIFLIK SİNYALİ: 50 Günlük Ortalama Kırıldı</b>\n\n"
                        f"Hisse: <b>{ticker}</b>\n"
                        f"Mevcut Fiyat: <b>${current_price:.2f}</b>\n"
                        f"50-Günlük SMA: ${sma_50:.2f}\n"
                        f"Hacim Oranı: <b>{volume_ratio:.2f}x</b>\n\n"
                        f"⚠️ Teknik destek kırıldı, pozisyon gözden geçirilmeli!"
                    )
                    self.notifier.send_message(message, priority="warning")
                    return True
        
        return False
    
    def check_volume_reversal(self, ticker, df, current_price, current_volume):
        """Hacimli ters dönüş kontrolü"""
        if len(df) < 10:
            return False
        
        prev_close = df['Close'].iloc[-2]
        price_change_pct = ((current_price - prev_close) / prev_close) * 100
        avg_volume_10d = df['Volume'].tail(10).mean()
        volume_ratio = current_volume / avg_volume_10d
        
        # %3'ten fazla düşüş + yüksek hacim
        if price_change_pct < -self.config['price_drop_threshold_pct']:
            if volume_ratio > self.config['volume_multiplier']:
                if self.can_send_alert(ticker, 'volume_reversal'):
                    message = (
                        f"<b>Hacimli Ters Dönüş Uyarısı</b>\n\n"
                        f"Hisse: <b>{ticker}</b>\n"
                        f"Mevcut Fiyat: <b>${current_price:.2f}</b>\n"
                        f"Önceki Kapanış: ${prev_close:.2f}\n"
                        f"Düşüş: <b>{price_change_pct:.2f}%</b>\n"
                        f"Hacim Oranı: <b>{volume_ratio:.2f}x</b> (10 günlük ort.)\n\n"
                        f"⚠️ Güçlü satış baskısı tespit edildi!"
                    )
                    self.notifier.send_message(message, priority="warning")
                    return True
        
        return False
    
    def monitor_position(self, row):
        """Tek bir pozisyonu izle ve tüm kuralları kontrol et"""
        ticker = row['Ticker']
        cost_basis = row['Maliyet']
        
        try:
            # Güncel veriyi çek
            stock = yf.Ticker(ticker)
            df = stock.history(period="3mo")
            
            if len(df) < 2:
                print(f"⚠ {ticker}: Yeterli veri yok")
                return
            
            current_price = df['Close'].iloc[-1]
            current_volume = df['Volume'].iloc[-1]
            
            print(f"📊 {ticker}: ${current_price:.2f} (Maliyet: ${cost_basis:.2f})")
            
            # Tüm kontrolleri yap
            self.check_hard_stop(ticker, current_price, cost_basis)
            self.check_backstop(row, current_price)
            self.check_sma_break(ticker, df, current_price, current_volume)
            self.check_volume_reversal(ticker, df, current_price, current_volume)
            
        except Exception as e:
            print(f"✗ {ticker} izleme hatası: {e}")
    
    def run_monitoring_cycle(self):
        """Tüm portföyü bir kez tara"""
        if self.portfolio.empty:
            print("⚠ Portföy boş, izlenecek hisse yok")
            return
        
        print("\n" + "=" * 80)
        print(f"🔍 Portföy İzleme Başladı - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        for idx, row in self.portfolio.iterrows():
            self.monitor_position(row)
            time.sleep(1)  # API rate limit
        
        print("=" * 80)
        print("✓ İzleme döngüsü tamamlandı\n")
    
    def run_continuous(self, interval_minutes=15):
        """Sürekli izleme modunda çalış"""
        print(f"\n🚀 Sürekli İzleme Modu Başlatıldı (Her {interval_minutes} dakikada bir)")
        print("Durdurmak için Ctrl+C basın\n")
        
        try:
            while True:
                self.run_monitoring_cycle()
                
                # Piyasa saatleri kontrolü (opsiyonel)
                now = datetime.now()
                if now.weekday() < 5:  # Pazartesi-Cuma
                    if 9 <= now.hour < 16:  # 09:00-16:00 arası aktif
                        print(f"⏰ Sonraki kontrol {interval_minutes} dakika sonra...")
                    else:
                        print(f"😴 Piyasa kapalı, sonraki kontrol {interval_minutes} dakika sonra...")
                else:
                    print(f"😴 Hafta sonu, sonraki kontrol {interval_minutes} dakika sonra...")
                
                time.sleep(interval_minutes * 60)
                
        except KeyboardInterrupt:
            print("\n\n⚠ İzleme durduruldu!")

def create_sample_portfolio():
    """Örnek portföy dosyası oluştur"""
    sample_data = {
        'Ticker': ['AAPL', 'NVDA', 'GOOGL'],
        'Maliyet': [150.00, 200.00, 280.00],
        'Adet': [10, 5, 8],
        'Alış_Tarihi': ['2024-01-15', '2024-02-01', '2024-02-10'],
        'Stop_Seviyesi': [139.50, 186.00, 260.40],
        'Backstop_Aktif': [False, False, False]
    }
    
    df = pd.DataFrame(sample_data)
    filename = 'my_portfolio.csv'
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"✓ Örnek portföy oluşturuldu: {filename}")
    return filename

def create_config_file():
    """Telegram config dosyası oluştur"""
    config = {
        "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
        "telegram_chat_id": "YOUR_CHAT_ID_HERE",
        "hard_stop_pct": 7.0,
        "profit_target_for_backstop": 15.0,
        "sma_period": 50,
        "price_drop_threshold_pct": 3.0,
        "volume_multiplier": 1.0,
        "alert_cooldown_minutes": 60,
        "monitoring_interval_minutes": 15
    }
    
    filename = 'telegram_config.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Config dosyası oluşturuldu: {filename}")
    return filename

def main():
    print("=" * 80)
    print("Mark Minervini Portföy İzleme ve Telegram Uyarı Sistemi")
    print("=" * 80)
    
    # Config ve portföy dosyalarını kontrol et
    config_file = 'telegram_config.json'
    portfolio_file = 'my_portfolio.csv'
    
    if not os.path.exists(config_file):
        print("\n⚠ telegram_config.json bulunamadı, oluşturuluyor...")
        create_config_file()
        print("\n❗ ÖNEMLI: telegram_config.json dosyasını düzenleyip Bot Token ve Chat ID'nizi ekleyin!")
        print("Nasıl yapılır:")
        print("1. @BotFather ile yeni bot oluşturun ve token'ı alın")
        print("2. @userinfobot ile chat ID'nizi öğrenin")
        print("3. telegram_config.json dosyasına bu bilgileri girin\n")
        return
    
    if not os.path.exists(portfolio_file):
        print("\n⚠ my_portfolio.csv bulunamadı, örnek portföy oluşturuluyor...")
        create_sample_portfolio()
        print("\n❗ ÖNEMLI: my_portfolio.csv dosyasını kendi hisselerinizle güncelleyin!")
        print("Sütunlar: Ticker, Maliyet, Adet, Alış_Tarihi, Stop_Seviyesi, Backstop_Aktif\n")
        return
    
    # Config'i yükle
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Telegram token kontrolü
    if config['telegram_bot_token'] == 'YOUR_BOT_TOKEN_HERE':
        print("\n❗ Lütfen telegram_config.json dosyasında Bot Token'ınızı ayarlayın!")
        return
    
    # Telegram notifier'ı oluştur
    notifier = TelegramNotifier(
        config['telegram_bot_token'],
        config['telegram_chat_id']
    )
    
    # Test mesajı gönder
    print("\n📱 Telegram bağlantısı test ediliyor...")
    test_msg = (
        f"<b>Portföy İzleme Sistemi Başladı</b>\n\n"
        f"✅ Sistem aktif ve çalışıyor\n"
        f"📊 İzleme aralığı: {config['monitoring_interval_minutes']} dakika\n"
        f"⏰ Başlama zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    if notifier.send_message(test_msg, priority="info"):
        print("✓ Telegram bağlantısı başarılı!\n")
    else:
        print("✗ Telegram bağlantısı başarısız! Token ve Chat ID'yi kontrol edin.\n")
        return
    
    # Portföy monitörünü başlat
    monitor = PortfolioMonitor(portfolio_file, config_file, notifier)
    
    # Kullanıcıya seçim sun
    print("\nİzleme modu seçin:")
    print("1. Tek kontrol (bir kez çalıştır)")
    print("2. Sürekli izleme (her 15 dakikada bir)")
    
    choice = input("\nSeçiminiz (1 veya 2): ").strip()
    
    if choice == "1":
        monitor.run_monitoring_cycle()
    elif choice == "2":
        monitor.run_continuous(interval_minutes=config['monitoring_interval_minutes'])
    else:
        print("Geçersiz seçim!")

if __name__ == "__main__":
    main()

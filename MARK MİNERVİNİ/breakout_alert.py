#!/usr/bin/env python3
"""
Breakout Uyarı Sistemi
BIST ve ABD hisseleri için pivot kırılımı takibi ve Telegram uyarıları
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

class BreakoutAlert:
    """Breakout uyarı sistemi"""
    
    def __init__(self, watchlist_file, config_file):
        self.watchlist_file = watchlist_file
        self.config_file = config_file
        self.watchlist = self.load_watchlist()
        self.config = self.load_config()
        self.alert_history = {}
        
        # Telegram
        if self.config.get('telegram_enabled'):
            self.bot_token = self.config['telegram_bot_token']
            self.chat_id = self.config['telegram_chat_id']
            self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
    
    def load_watchlist(self):
        """Watchlist dosyasını yükle"""
        try:
            if os.path.exists(self.watchlist_file):
                df = pd.read_csv(self.watchlist_file)
                print(f"✓ Watchlist yüklendi: {len(df)} hisse izleniyor")
                return df
            else:
                print(f"⚠ Watchlist dosyası bulunamadı: {self.watchlist_file}")
                return pd.DataFrame()
        except Exception as e:
            print(f"✗ Watchlist yükleme hatası: {e}")
            return pd.DataFrame()
    
    def load_config(self):
        """Config dosyasını yükle"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {
                    "telegram_enabled": True,
                    "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
                    "telegram_chat_id": "YOUR_CHAT_ID_HERE",
                    "volume_spike_threshold": 1.5,
                    "stop_loss_pct": 7.0,
                    "check_interval_minutes": 5,
                    "market_hours_only": False
                }
        except Exception as e:
            print(f"✗ Config yükleme hatası: {e}")
            return {}
    
    def send_telegram(self, message, priority="normal"):
        """Telegram mesajı gönder"""
        if not self.config.get('telegram_enabled'):
            print("ℹ Telegram devre dışı")
            return False
        
        try:
            if priority == "critical":
                message = f"🚨 ACİL 🚨\n\n{message}"
            elif priority == "buy":
                message = f"💰 ALIM SİNYALİ\n\n{message}"
            elif priority == "sell":
                message = f"🔴 SATIM SİNYALİ\n\n{message}"
            
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
                print(f"✗ Telegram hatası: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"✗ Telegram gönderim hatası: {e}")
            return False
    
    def check_breakout(self, row):
        """Breakout kontrolü"""
        ticker = row['Ticker']
        market = row['Market']
        pivot = row['Pivot']
        stop_level = row['Stop_Level']
        
        # Yahoo Finance ticker formatı
        yahoo_ticker = f"{ticker}.IS" if market == 'BIST' else ticker
        
        try:
            # Güncel veriyi çek
            stock = yf.Ticker(yahoo_ticker)
            df = stock.history(period="5d")
            
            if len(df) < 2:
                return None
            
            current_price = df['Close'].iloc[-1]
            current_volume = df['Volume'].iloc[-1]
            avg_volume = df['Volume'].tail(20).mean() if len(df) >= 20 else df['Volume'].mean()
            
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            # BREAKOUT kontrolü: Pivot'u hacimli kırdı mı?
            if current_price > pivot:
                spike_threshold = self.config.get('volume_spike_threshold', 1.5)
                
                if volume_ratio >= spike_threshold:
                    # İlk kez mi breakout oluyor?
                    key = f"{ticker}_breakout"
                    if key not in self.alert_history:
                        self.alert_history[key] = datetime.now()
                        
                        # Telegram uyarısı
                        currency = "₺" if market == 'BIST' else "$"
                        flag = "🇹🇷" if market == 'BIST' else "🇺🇸"
                        
                        message = (
                            f"<b>MINERVINI BUY ALERT</b>\n\n"
                            f"{flag} <b>{market} - {ticker}</b>\n\n"
                            f"✅ Pivot Kırıldı!\n"
                            f"Fiyat: <b>{currency}{current_price:.2f}</b>\n"
                            f"Pivot: {currency}{pivot:.2f}\n"
                            f"Hacim: <b>{volume_ratio:.2f}x</b> (Normal: 1.0x)\n\n"
                            f"📊 ALIM BİLGİLERİ:\n"
                            f"Giriş: {currency}{current_price:.2f}\n"
                            f"Stop: {currency}{stop_level:.2f} (-7%)\n"
                            f"Risk: {currency}{abs(current_price - stop_level):.2f}\n\n"
                            f"⚠️ Stop-loss'u mutlaka kullanın!"
                        )
                        
                        self.send_telegram(message, priority="buy")
                        
                        return {
                            'Type': 'BREAKOUT',
                            'Ticker': ticker,
                            'Market': market,
                            'Price': current_price,
                            'Pivot': pivot,
                            'Volume_Ratio': volume_ratio
                        }
            
            # STOP-LOSS kontrolü
            if current_price <= stop_level:
                key = f"{ticker}_stop"
                
                # Son 60 dakikada bu uyarı gönderildi mi?
                if key in self.alert_history:
                    last_alert = self.alert_history[key]
                    if datetime.now() - last_alert < timedelta(minutes=60):
                        return None
                
                self.alert_history[key] = datetime.now()
                
                # Telegram uyarısı
                currency = "₺" if market == 'BIST' else "$"
                flag = "🇹🇷" if market == 'BIST' else "🇺🇸"
                
                loss_pct = ((current_price - stop_level) / stop_level) * 100
                
                message = (
                    f"<b>EXIT SIGNAL</b>\n\n"
                    f"{flag} <b>{market} - {ticker}</b>\n\n"
                    f"❌ Stop-Loss Seviyesi!\n"
                    f"Fiyat: <b>{currency}{current_price:.2f}</b>\n"
                    f"Stop: {currency}{stop_level:.2f}\n"
                    f"Zarar: <b>{loss_pct:.2f}%</b>\n\n"
                    f"⚠️ Derhal pozisyonu kapat!"
                )
                
                self.send_telegram(message, priority="sell")
                
                return {
                    'Type': 'STOP_HIT',
                    'Ticker': ticker,
                    'Market': market,
                    'Price': current_price,
                    'Stop': stop_level
                }
            
            # Pivot'a yakınlık güncelleme
            distance = ((pivot - current_price) / pivot) * 100
            
            if 0 < distance <= 0.5:  # %0.5'ten yakın
                key = f"{ticker}_near"
                
                # Son 30 dakikada bu uyarı gönderildi mi?
                if key in self.alert_history:
                    last_alert = self.alert_history[key]
                    if datetime.now() - last_alert < timedelta(minutes=30):
                        return None
                
                self.alert_history[key] = datetime.now()
                
                currency = "₺" if market == 'BIST' else "$"
                flag = "🇹🇷" if market == 'BIST' else "🇺🇸"
                
                message = (
                    f"<b>Pivot Yaklaşım Uyarısı</b>\n\n"
                    f"{flag} <b>{market} - {ticker}</b>\n\n"
                    f"📍 Pivot'a Çok Yakın!\n"
                    f"Fiyat: {currency}{current_price:.2f}\n"
                    f"Pivot: {currency}{pivot:.2f}\n"
                    f"Mesafe: <b>%{distance:.2f}</b>\n"
                    f"Hacim: {volume_ratio:.2f}x\n\n"
                    f"👀 Yakından izleyin!"
                )
                
                self.send_telegram(message, priority="normal")
            
            return None
            
        except Exception as e:
            print(f"✗ {ticker} kontrol hatası: {e}")
            return None
    
    def run_monitoring_cycle(self):
        """Tek kontrol döngüsü"""
        if self.watchlist.empty:
            print("⚠ Watchlist boş")
            return
        
        print("\n" + "=" * 80)
        print(f"🔍 Breakout İzleme - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        alerts = []
        
        for idx, row in self.watchlist.iterrows():
            ticker = row['Ticker']
            market = row['Market']
            
            print(f"📊 {market} - {ticker} kontrol ediliyor...", end=' ')
            
            alert = self.check_breakout(row)
            
            if alert:
                alerts.append(alert)
                print(f"✓ {alert['Type']}")
            else:
                print("—")
            
            time.sleep(0.5)  # Rate limit
        
        print("=" * 80)
        
        if alerts:
            print(f"\n🎯 {len(alerts)} uyarı oluşturuldu!")
            for alert in alerts:
                print(f"  • {alert['Market']} - {alert['Ticker']}: {alert['Type']}")
        else:
            print("\n✓ Kontrol tamamlandı, yeni uyarı yok")
        
        print()
    
    def run_continuous(self):
        """Sürekli izleme modu"""
        interval = self.config.get('check_interval_minutes', 5)
        market_hours_only = self.config.get('market_hours_only', False)
        
        print(f"\n🚀 Sürekli İzleme Modu Başladı")
        print(f"Kontrol aralığı: {interval} dakika")
        print(f"Piyasa saatleri sınırı: {'Evet' if market_hours_only else 'Hayır'}")
        print("Durdurmak için Ctrl+C basın\n")
        
        # İlk test mesajı
        if self.config.get('telegram_enabled'):
            self.send_telegram(
                f"<b>Breakout İzleme Başladı</b>\n\n"
                f"✅ Sistem aktif\n"
                f"📊 {len(self.watchlist)} hisse izleniyor\n"
                f"⏰ Kontrol aralığı: {interval} dk",
                priority="normal"
            )
        
        try:
            while True:
                now = datetime.now()
                
                # Piyasa saatleri kontrolü (opsiyonel)
                if market_hours_only:
                    if now.weekday() >= 5:  # Hafta sonu
                        print(f"😴 Hafta sonu - Bekleniyor...")
                        time.sleep(interval * 60)
                        continue
                    
                    # ABD: 09:30 - 16:00 ET
                    # BIST: 10:00 - 18:00 TRT
                    # Basitleştirilmiş kontrol
                    if not (9 <= now.hour < 19):
                        print(f"😴 Piyasa kapalı - Bekleniyor...")
                        time.sleep(interval * 60)
                        continue
                
                self.run_monitoring_cycle()
                
                print(f"⏰ Sonraki kontrol {interval} dakika sonra ({(now + timedelta(minutes=interval)).strftime('%H:%M')})")
                time.sleep(interval * 60)
                
        except KeyboardInterrupt:
            print("\n\n⚠ İzleme durduruldu!")
            
            if self.config.get('telegram_enabled'):
                self.send_telegram(
                    f"<b>Breakout İzleme Durduruldu</b>\n\n"
                    f"⏸ Sistem kapatıldı\n"
                    f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    priority="normal"
                )

def create_sample_watchlist():
    """Örnek watchlist oluştur"""
    sample = {
        'Market': ['US', 'US', 'BIST', 'BIST'],
        'Ticker': ['NVDA', 'AMD', 'GARAN', 'THYAO'],
        'Price': [200.0, 150.0, 45.0, 300.0],
        'Pivot': [205.0, 155.0, 46.5, 310.0],
        'Stop_Level': [186.0, 139.5, 41.85, 279.0],
        'Status': ['PIVOT_NEAR', 'PIVOT_NEAR', 'SETUP', 'SETUP']
    }
    
    df = pd.DataFrame(sample)
    filename = 'breakout_watchlist.csv'
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"✓ Örnek watchlist oluşturuldu: {filename}")
    return filename

def create_breakout_config():
    """Config dosyası oluştur"""
    config = {
        "telegram_enabled": True,
        "telegram_bot_token": "YOUR_BOT_TOKEN_HERE",
        "telegram_chat_id": "YOUR_CHAT_ID_HERE",
        "volume_spike_threshold": 1.5,
        "stop_loss_pct": 7.0,
        "check_interval_minutes": 5,
        "market_hours_only": False
    }
    
    filename = 'breakout_config.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Config dosyası oluşturuldu: {filename}")
    return filename

def main():
    print("=" * 80)
    print("Breakout Uyarı Sistemi - BIST + ABD Borsaları")
    print("=" * 80)
    
    config_file = 'breakout_config.json'
    watchlist_file = 'breakout_watchlist.csv'
    
    # Config kontrolü
    if not os.path.exists(config_file):
        print("\n⚠ breakout_config.json bulunamadı, oluşturuluyor...")
        create_breakout_config()
        print("\n❗ ÖNEMLI: breakout_config.json dosyasına Telegram bilgilerinizi ekleyin!")
        print("(telegram_config.json ile aynı bot'u kullanabilirsiniz)\n")
        return
    
    # Watchlist kontrolü
    if not os.path.exists(watchlist_file):
        print("\n⚠ breakout_watchlist.csv bulunamadı...")
        
        # En son universal scan sonucunu ara
        import glob
        scan_files = glob.glob("universal_scan_*.csv")
        
        if scan_files:
            latest_scan = sorted(scan_files)[-1]
            print(f"✓ En son tarama bulundu: {latest_scan}")
            print("Bu dosyadaki BREAKOUT ve PIVOT_NEAR hisseler watchlist'e aktarılacak...\n")
            
            df = pd.read_csv(latest_scan)
            watchlist = df[df['Status'].isin(['BREAKOUT', 'PIVOT_NEAR'])]
            
            if len(watchlist) > 0:
                watchlist.to_csv(watchlist_file, index=False, encoding='utf-8-sig')
                print(f"✓ {len(watchlist)} hisse watchlist'e eklendi")
            else:
                print("⚠ BREAKOUT/PIVOT_NEAR hisse bulunamadı, örnek watchlist oluşturuluyor...")
                create_sample_watchlist()
        else:
            print("⚠ Önce universal_scanner.py çalıştırın veya manuel watchlist oluşturun")
            create_sample_watchlist()
            return
    
    # Config yükle
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if config['telegram_bot_token'] == 'YOUR_BOT_TOKEN_HERE':
        print("\n❗ Lütfen breakout_config.json dosyasında Telegram bilgilerini ayarlayın!")
        return
    
    # Alert sistemi başlat
    alert_system = BreakoutAlert(watchlist_file, config_file)
    
    if alert_system.watchlist.empty:
        print("\n⚠ Watchlist boş!")
        return
    
    print(f"\n📊 Watchlist: {len(alert_system.watchlist)} hisse")
    print("\nİzleme modu seçin:")
    print("1. Tek kontrol (test için)")
    print("2. Sürekli izleme (her 5 dakikada)")
    
    choice = input("\nSeçiminiz (1 veya 2): ").strip()
    
    if choice == "1":
        alert_system.run_monitoring_cycle()
    elif choice == "2":
        alert_system.run_continuous()
    else:
        print("Geçersiz seçim!")

if __name__ == "__main__":
    main()

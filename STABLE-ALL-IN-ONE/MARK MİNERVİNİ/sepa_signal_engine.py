#!/usr/bin/env python3
"""
SEPA Sinyal Motoru ve Otomasyon Sistemi
Otomatik Alım/Satım Sinyali Üretimi + Telegram Webhook
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import time
import requests
import os
import warnings
warnings.filterwarnings('ignore')

class SEPASignalEngine:
    """SEPA Sinyal Motoru - Alım/Satım Sinyalleri"""
    
    def __init__(self, config_file="sepa_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.active_positions = {}  # {ticker: {entry, stop, ...}}
        self.signal_history = []
        
    def load_config(self):
        """Konfigürasyon yükle"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Varsayılan config
            default_config = {
                "telegram_enabled": True,
                "telegram_bot_token": "YOUR_BOT_TOKEN",
                "telegram_chat_id": "YOUR_CHAT_ID",
                "webhook_url": None,
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
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            
            return default_config
    
    def send_telegram(self, message, priority="normal"):
        """Telegram mesajı gönder"""
        if not self.config.get('telegram_enabled'):
            return False
        
        try:
            if priority == "buy":
                message = f"💰 BUY_SIGNAL\n\n{message}"
            elif priority == "sell":
                message = f"🔴 SELL_WARNING\n\n{message}"
            
            api_url = f"https://api.telegram.org/bot{self.config['telegram_bot_token']}/sendMessage"
            
            payload = {
                'chat_id': self.config['telegram_chat_id'],
                'text': message,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(api_url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"Telegram hatası: {e}")
            return False
    
    def send_webhook(self, signal_data):
        """Webhook'a sinyal gönder"""
        webhook_url = self.config.get('webhook_url')
        if not webhook_url:
            return False
        
        try:
            response = requests.post(webhook_url, json=signal_data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Webhook hatası: {e}")
            return False
    
    def check_buy_signal(self, scan_result):
        """Alım sinyali kontrolü"""
        ticker = scan_result['ticker']
        market = scan_result['market']
        
        # Zaten pozisyon var mı?
        if ticker in self.active_positions:
            return None
        
        # BREAKOUT veya PIVOT_TOUCH durumu
        if scan_result['status'] not in ['BREAKOUT', 'PIVOT_TOUCH']:
            return None
        
        try:
            # Güncel veriyi çek
            yahoo_ticker = f"{ticker}.IS" if market == 'BIST' else ticker
            stock = yf.Ticker(yahoo_ticker)
            df = stock.history(period="5d")
            
            if len(df) < 2:
                return None
            
            current_price = df['Close'].iloc[-1]
            pivot = scan_result['pivot_price']
            
            # Hacim kontrolü
            avg_volume = df['Volume'].tail(20).mean() if len(df) >= 20 else df['Volume'].mean()
            current_volume = df['Volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            # Giriş sinyali: Pivot'u hacimli kırdı mı?
            threshold = self.config.get('volume_spike_threshold', 1.5)
            
            if current_price > pivot and volume_ratio >= threshold:
                # BUY_SIGNAL üret
                signal = {
                    "signal_type": "BUY_SIGNAL",
                    "ticker": ticker,
                    "market": market,
                    "entry_price": round(current_price, 2),
                    "pivot_price": pivot,
                    "stop_loss": scan_result['stop_loss'],
                    "volume_ratio": round(volume_ratio, 2),
                    "rs_rank": scan_result['rs_rank'],
                    "timestamp": datetime.now().isoformat(),
                    "vcp_confirmed": scan_result['vcp_details']['is_tight']
                }
                
                # Pozisyonu kaydet
                self.active_positions[ticker] = {
                    "entry_price": current_price,
                    "stop_loss": scan_result['stop_loss'],
                    "breakeven_moved": False,
                    "market": market,
                    "entry_date": datetime.now().isoformat()
                }
                
                # Sinyal geçmişi
                self.signal_history.append(signal)
                
                # Telegram bildirim
                currency = "₺" if market == 'BIST' else "$"
                flag = "🇹🇷" if market == 'BIST' else "🇺🇸"
                
                message = (
                    f"<b>MINERVINI BUY ALERT</b>\n\n"
                    f"{flag} <b>{market} - {ticker}</b>\n\n"
                    f"✅ Pivot Kırıldı! (Hacimli)\n"
                    f"Giriş: <b>{currency}{current_price:.2f}</b>\n"
                    f"Pivot: {currency}{pivot:.2f}\n"
                    f"Hacim: <b>{volume_ratio:.2f}x</b>\n"
                    f"RS Rank: {scan_result['rs_rank']}\n\n"
                    f"📊 POZİSYON BİLGİLERİ:\n"
                    f"Stop-Loss: {currency}{scan_result['stop_loss']:.2f} (-7%)\n"
                    f"Hedef 1: {currency}{current_price * 1.15:.2f} (+15%)\n\n"
                    f"⚠️ VCP Confirmed: {'✅' if signal['vcp_confirmed'] else '❌'}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
                
                self.send_telegram(message, priority="buy")
                self.send_webhook(signal)
                
                print(f"\n🚀 BUY_SIGNAL: {ticker} @ {currency}{current_price:.2f}")
                
                return signal
            
        except Exception as e:
            print(f"Buy signal kontrolü hatası: {e}")
            return None
    
    def check_sell_signals(self):
        """Satış sinyali kontrolü (tüm aktif pozisyonlar için)"""
        signals = []
        
        for ticker, position in list(self.active_positions.items()):
            market = position['market']
            entry_price = position['entry_price']
            stop_loss = position['stop_loss']
            breakeven_moved = position.get('breakeven_moved', False)
            
            try:
                yahoo_ticker = f"{ticker}.IS" if market == 'BIST' else ticker
                stock = yf.Ticker(yahoo_ticker)
                df = stock.history(period="60d")
                
                if len(df) < 50:
                    continue
                
                current_price = df['Close'].iloc[-1]
                current_volume = df['Volume'].iloc[-1]
                
                # Kâr/Zarar hesapla
                profit_pct = ((current_price - entry_price) / entry_price) * 100
                
                # 1. Hard Stop: %7 düşüş
                if current_price <= stop_loss:
                    signal = self._create_sell_signal(
                        ticker, market, current_price, entry_price,
                        "HARD_STOP", profit_pct,
                        "Fiyat stop-loss seviyesine ulaştı (-7%)"
                    )
                    signals.append(signal)
                    del self.active_positions[ticker]
                    continue
                
                # 2. Profit Protection: %15 kâr -> Stop'u başabaşa çek
                profit_target = self.config.get('profit_target_pct', 15.0)
                if profit_pct >= profit_target and not breakeven_moved:
                    # Stop'u başabaşa çek
                    self.active_positions[ticker]['stop_loss'] = entry_price
                    self.active_positions[ticker]['breakeven_moved'] = True
                    
                    currency = "₺" if market == 'BIST' else "$"
                    flag = "🇹🇷" if market == 'BIST' else "🇺🇸"
                    
                    message = (
                        f"<b>Profit Protection Aktif</b>\n\n"
                        f"{flag} <b>{market} - {ticker}</b>\n\n"
                        f"✅ %15 Kâr Hedefine Ulaşıldı!\n"
                        f"Mevcut: {currency}{current_price:.2f}\n"
                        f"Giriş: {currency}{entry_price:.2f}\n"
                        f"Kâr: <b>+{profit_pct:.2f}%</b>\n\n"
                        f"📊 Stop seviyesi başabaşa çekildi:\n"
                        f"Yeni Stop: <b>{currency}{entry_price:.2f}</b>\n\n"
                        f"💰 Artık risksiz kâr takibi!"
                    )
                    
                    self.send_telegram(message, priority="normal")
                    print(f"✅ {ticker}: Stop başabaşa çekildi")
                
                # 3. Technical Failure: 50G SMA altında hacimli kapanış
                sma_50 = df['Close'].rolling(window=50).mean().iloc[-1]
                avg_volume = df['Volume'].tail(20).mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
                
                if current_price < sma_50 and volume_ratio > 1.3:
                    signal = self._create_sell_signal(
                        ticker, market, current_price, entry_price,
                        "TECHNICAL_FAILURE", profit_pct,
                        f"50G SMA altında hacimli kapanış (Hacim: {volume_ratio:.2f}x)"
                    )
                    signals.append(signal)
                
                # 4. High Volume Reversal: Yüksek hacimli geri dönüş
                prev_close = df['Close'].iloc[-2]
                price_change_pct = ((current_price - prev_close) / prev_close) * 100
                
                if price_change_pct < -3.0 and volume_ratio > 1.5:
                    signal = self._create_sell_signal(
                        ticker, market, current_price, entry_price,
                        "HIGH_VOLUME_REVERSAL", profit_pct,
                        f"Yüksek hacimli geri dönüş (-{abs(price_change_pct):.2f}%, Hacim: {volume_ratio:.2f}x)"
                    )
                    signals.append(signal)
                
            except Exception as e:
                print(f"{ticker} sell signal kontrolü hatası: {e}")
                continue
        
        return signals
    
    def _create_sell_signal(self, ticker, market, current_price, entry_price, 
                           signal_type, profit_pct, reason):
        """Satış sinyali oluştur"""
        signal = {
            "signal_type": "SELL_WARNING",
            "sell_reason": signal_type,
            "ticker": ticker,
            "market": market,
            "current_price": round(current_price, 2),
            "entry_price": round(entry_price, 2),
            "profit_loss_pct": round(profit_pct, 2),
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        
        self.signal_history.append(signal)
        
        # Telegram bildirim
        currency = "₺" if market == 'BIST' else "$"
        flag = "🇹🇷" if market == 'BIST' else "🇺🇸"
        
        pnl_emoji = "📈" if profit_pct > 0 else "📉"
        
        message = (
            f"<b>SELL WARNING</b>\n\n"
            f"{flag} <b>{market} - {ticker}</b>\n\n"
            f"⚠️ Satış Sinyali: <b>{signal_type}</b>\n\n"
            f"Sebep: {reason}\n\n"
            f"Mevcut: {currency}{current_price:.2f}\n"
            f"Giriş: {currency}{entry_price:.2f}\n"
            f"{pnl_emoji} P/L: <b>{profit_pct:+.2f}%</b>\n\n"
            f"🔴 Pozisyonu kapatmayı değerlendirin!"
        )
        
        self.send_telegram(message, priority="sell")
        self.send_webhook(signal)
        
        print(f"\n🔴 SELL_WARNING: {ticker} - {signal_type}")
        
        return signal
    
    def save_signal_history(self, filename="sepa_signal_history.json"):
        """Sinyal geçmişini kaydet"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.signal_history, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Kaydetme hatası: {e}")
            return False
    
    def is_market_hours(self, market="US"):
        """Piyasa saatleri kontrolü"""
        now = datetime.now()
        
        # Hafta sonu kontrolü
        if now.weekday() >= 5:
            return False
        
        current_time = now.strftime("%H:%M")
        
        if market == "US":
            market_open = self.config['market_hours']['us_open']
            market_close = self.config['market_hours']['us_close']
        else:  # BIST
            market_open = self.config['market_hours']['bist_open']
            market_close = self.config['market_hours']['bist_close']
        
        return market_open <= current_time <= market_close
    
    def is_optimal_scan_time(self):
        """Optimal tarama zamanı mı? (İlk 30 dk ve son 30 dk)"""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        # ABD: 09:30-10:00 ve 15:30-16:00
        us_morning = "09:30" <= current_time <= "10:00"
        us_evening = "15:30" <= current_time <= "16:00"
        
        # BIST: 10:00-10:30 ve 17:30-18:00
        bist_morning = "10:00" <= current_time <= "10:30"
        bist_evening = "17:30" <= current_time <= "18:00"
        
        return us_morning or us_evening or bist_morning or bist_evening
    
    def run_continuous_monitoring(self, scan_results_file):
        """Sürekli izleme modu"""
        print("\n" + "=" * 80)
        print("SEPA SİNYAL MOTORU - SÜREKLİ İZLEME MODU")
        print("=" * 80)
        print(f"✓ Aktif Pozisyonlar: {len(self.active_positions)}")
        print(f"✓ Tarama Aralığı: {self.config['check_interval_minutes']} dakika")
        print("Durdurmak için Ctrl+C\n")
        
        try:
            while True:
                # Tarama sonuçlarını yükle
                if os.path.exists(scan_results_file):
                    with open(scan_results_file, 'r', encoding='utf-8') as f:
                        scan_results = json.load(f)
                    
                    print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"📊 Tarama sonuçları: {len(scan_results)} hisse")
                    
                    # Optimal tarama zamanı mı?
                    if self.is_optimal_scan_time():
                        print("🎯 Optimal tarama zamanı - Aktif kontrol")
                    
                    # Alım sinyali kontrolü
                    for result in scan_results:
                        if result['status'] in ['BREAKOUT', 'PIVOT_TOUCH']:
                            self.check_buy_signal(result)
                    
                    # Satış sinyali kontrolü
                    if self.active_positions:
                        print(f"📈 {len(self.active_positions)} aktif pozisyon izleniyor...")
                        sell_signals = self.check_sell_signals()
                        
                        if sell_signals:
                            print(f"⚠️ {len(sell_signals)} satış uyarısı!")
                    
                    # Sinyal geçmişini kaydet
                    self.save_signal_history()
                
                # Bekleme
                interval = self.config['check_interval_minutes']
                print(f"\n😴 {interval} dakika bekleniyor...")
                time.sleep(interval * 60)
                
        except KeyboardInterrupt:
            print("\n\n⚠️ İzleme durduruldu!")
            self.save_signal_history()

def main():
    print("=" * 80)
    print("SEPA Sinyal Motoru - Otomasyon Sistemi")
    print("=" * 80)
    
    # Config kontrolü
    if not os.path.exists("sepa_config.json"):
        print("\n⚠️ sepa_config.json oluşturuluyor...")
        engine = SEPASignalEngine()
        print("✓ Config oluşturuldu")
        print("\n❗ ÖNEMLI: sepa_config.json dosyasına Telegram bilgilerinizi ekleyin!")
        return
    
    # En son tarama sonucunu bul
    import glob
    scan_files = glob.glob("sepa_scan_*.json")
    
    if not scan_files:
        print("\n⚠️ Tarama sonucu bulunamadı!")
        print("Önce 'python3 sepa_scanner.py' çalıştırın")
        return
    
    latest_scan = sorted(scan_files)[-1]
    print(f"\n📂 Tarama sonucu: {latest_scan}")
    
    # Engine başlat
    engine = SEPASignalEngine()
    
    print("\nMod seçin:")
    print("1. Tek kontrol (test)")
    print("2. Sürekli izleme")
    
    choice = input("\nSeçim (1 veya 2): ").strip()
    
    if choice == "2":
        engine.run_continuous_monitoring(latest_scan)
    else:
        # Tek kontrol
        with open(latest_scan, 'r', encoding='utf-8') as f:
            scan_results = json.load(f)
        
        print(f"\n📊 {len(scan_results)} hisse kontrol ediliyor...")
        
        for result in scan_results:
            if result['status'] in ['BREAKOUT', 'PIVOT_TOUCH']:
                signal = engine.check_buy_signal(result)
                if signal:
                    print(f"✓ {signal['ticker']}: BUY_SIGNAL")

if __name__ == "__main__":
    main()

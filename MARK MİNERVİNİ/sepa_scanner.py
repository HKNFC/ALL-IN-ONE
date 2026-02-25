#!/usr/bin/env python3
"""
Mark Minervini SEPA Metodolojisi - Profesyonel Tarama Sistemi
Trend Template 2.0 + VCP + JSON Sinyal Üretimi
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

class SEPAScanner:
    """Mark Minervini SEPA Metodolojisi Scanner"""
    
    def __init__(self):
        self.results = []
        
    def calculate_sma(self, df, period):
        """SMA hesapla"""
        return df['Close'].rolling(window=period).mean()
    
    def check_sma_uptrend(self, df, period=200, days=30):
        """SMA'nın en az 1 aydır pozitif eğimli olduğunu kontrol et"""
        if len(df) < period + days:
            return False
        
        sma = self.calculate_sma(df, period)
        
        # NaN kontrol
        if pd.isna(sma.iloc[-1]) or pd.isna(sma.iloc[-days]):
            return False
        
        return sma.iloc[-1] > sma.iloc[-days]
    
    def calculate_ibd_rs(self, stock_df, market_df):
        """IBD tarzı Relative Strength hesapla (0-99 skala)"""
        try:
            if len(stock_df) < 252 or len(market_df) < 252:
                return None
            
            # Son 1 yıllık performansı ağırlıklandır
            # IBD: %40 son 3 ay, %20 6-12 ay önce, %40 3-6 ay
            
            periods = {
                'q1': (0, 63),      # Son 3 ay (252 gün / 4)
                'q2': (63, 126),    # 3-6 ay önce
                'q3': (126, 189),   # 6-9 ay önce
                'q4': (189, 252)    # 9-12 ay önce
            }
            
            stock_returns = {}
            market_returns = {}
            
            for period, (start, end) in periods.items():
                stock_slice = stock_df['Close'].iloc[-(end+1):-(start+1) if start > 0 else None]
                market_slice = market_df['Close'].iloc[-(end+1):-(start+1) if start > 0 else None]
                
                if len(stock_slice) > 0 and len(market_slice) > 0:
                    stock_returns[period] = (stock_slice.iloc[-1] / stock_slice.iloc[0] - 1) * 100
                    market_returns[period] = (market_slice.iloc[-1] / market_slice.iloc[0] - 1) * 100
                else:
                    return None
            
            # IBD ağırlıklandırma: Q1=40%, Q2=40%, Q3=20%
            weights = {'q1': 0.40, 'q2': 0.40, 'q3': 0.20, 'q4': 0.0}
            
            weighted_stock = sum(stock_returns[p] * weights[p] for p in ['q1', 'q2', 'q3'])
            weighted_market = sum(market_returns[p] * weights[p] for p in ['q1', 'q2', 'q3'])
            
            # Relative Strength hesapla ve 0-99 arasına normalize et
            rs_raw = ((1 + weighted_stock/100) / (1 + weighted_market/100) - 1) * 100
            rs_score = max(0, min(99, rs_raw + 50))
            
            return round(rs_score, 2)
            
        except Exception as e:
            return None
    
    def calculate_bist_rs_correlation(self, stock_df, xu100_df):
        """BIST için Sembol/XU100 rasyosu korelasyonu"""
        try:
            if len(stock_df) < 63 or len(xu100_df) < 63:  # 3 ay
                return None
            
            # Son 3 aylık veri
            stock_recent = stock_df['Close'].tail(63)
            xu100_recent = xu100_df['Close'].tail(63)
            
            # Normalize edilmiş fiyatlar (ilk güne göre)
            stock_normalized = stock_recent / stock_recent.iloc[0]
            xu100_normalized = xu100_recent / xu100_recent.iloc[0]
            
            # Rasyo
            ratio = stock_normalized / xu100_normalized
            
            # Linear regression slope (eğim) - pozitif ayrışma göstergesi
            x = np.arange(len(ratio))
            slope, _ = np.polyfit(x, ratio.values, 1)
            
            # Slope'u anlamlı bir metriğe çevir
            # Pozitif ve >0.002 ise güçlü ayrışma
            correlation_score = slope * 100
            
            return round(correlation_score, 4)
            
        except Exception as e:
            return None
    
    def detect_vcp_base(self, df):
        """VCP Base yapısı tespit et (3 aylık)"""
        try:
            if len(df) < 90:  # ~3 ay
                return None
            
            recent = df.tail(90)
            
            # Son 3 aydaki en yüksek
            three_month_high = recent['High'].max()
            current_price = recent['Close'].iloc[-1]
            
            # %25-30 içeride mi?
            pullback_pct = ((three_month_high - current_price) / three_month_high) * 100
            
            if not (25 <= pullback_pct <= 30):
                return None
            
            # Base yapısını haftalara böl (yaklaşık 6 hafta * 15 gün)
            weeks = []
            chunk_size = 15
            
            for i in range(0, len(recent), chunk_size):
                week_data = recent.iloc[i:i+chunk_size]
                if len(week_data) > 0:
                    high = week_data['High'].max()
                    low = week_data['Low'].min()
                    volatility = ((high - low) / low) * 100 if low > 0 else 0
                    avg_volume = week_data['Volume'].mean()
                    weeks.append({
                        'volatility': volatility,
                        'volume': avg_volume
                    })
            
            if len(weeks) < 3:
                return None
            
            # Volatilite daralması kontrolü (soldan sağa)
            volatilities = [w['volatility'] for w in weeks[-3:]]  # Son 3 hafta
            
            # Daralma var mı? Her periyot bir öncekinden küçük mü?
            contracting = all(volatilities[i] > volatilities[i+1] for i in range(len(volatilities)-1))
            
            # Son hafta %3'ün altında mı? (Tight)
            is_tight = volatilities[-1] < 3.0
            
            # Hacim azalması
            volumes = [w['volume'] for w in weeks[-3:]]
            volume_decreasing = all(volumes[i] > volumes[i+1] for i in range(len(volumes)-1))
            
            if contracting and (is_tight or volatilities[-1] < 5.0):
                return {
                    'in_base': True,
                    'pullback_pct': round(pullback_pct, 2),
                    'contractions': 2 if contracting else 0,
                    'last_volatility': round(volatilities[-1], 2),
                    'is_tight': is_tight,
                    'volume_decreasing': volume_decreasing,
                    'three_month_high': round(three_month_high, 2)
                }
            
            return None
            
        except Exception as e:
            return None
    
    def find_pivot_point(self, df, lookback=20):
        """Pivot noktası (direnç) bul"""
        if len(df) < lookback:
            return None, None
        
        recent = df.tail(lookback)
        pivot = recent['High'].max()
        current_price = df['Close'].iloc[-1]
        
        distance = ((pivot - current_price) / pivot) * 100
        
        return round(pivot, 2), round(distance, 2)
    
    def calculate_stop_loss(self, entry_price, stop_pct=7.0):
        """Stop-loss seviyesi hesapla"""
        return round(entry_price * (1 - stop_pct/100), 2)
    
    def check_volume_spike(self, df, threshold=1.5):
        """Hacim artışı kontrolü"""
        if len(df) < 20:
            return False, None
        
        avg_volume = df['Volume'].tail(20).mean()
        current_volume = df['Volume'].iloc[-1]
        
        ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        return ratio >= threshold, round(ratio, 2)
    
    def determine_status(self, current_price, pivot, distance, vcp_base, volume_spike_ratio):
        """Hisse durumunu belirle"""
        # BREAKOUT: Pivot'u hacimli kırdı
        if distance is not None and distance < 0 and volume_spike_ratio and volume_spike_ratio >= 1.5:
            return "BREAKOUT"
        
        # PIVOT_TOUCH: Pivot'a %1'den yakın ve VCP var
        if distance is not None and 0 <= distance <= 1.0 and vcp_base and vcp_base.get('is_tight'):
            return "PIVOT_TOUCH"
        
        # SETUP: VCP base'de ve pivot'tan uzak değil
        if vcp_base and distance is not None and distance <= 5.0:
            return "SETUP"
        
        return "WATCHING"
    
    def scan_us_stock(self, ticker, sp500_data, rs_threshold=85):
        """ABD hissesi tara - SEPA Trend Template 2.0"""
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y")
            
            if len(df) < 200:
                return None
            
            current_price = df['Close'].iloc[-1]
            sma_150 = self.calculate_sma(df, 150).iloc[-1]
            sma_200 = self.calculate_sma(df, 200).iloc[-1]
            sma_50 = self.calculate_sma(df, 50).iloc[-1]
            
            # NaN kontrolü
            if pd.isna(sma_150) or pd.isna(sma_200) or pd.isna(sma_50):
                return None
            
            # Kriter 1: Fiyat > 150G ve 200G SMA
            if not (current_price > sma_150 and current_price > sma_200):
                return None
            
            # Kriter 2: 200G SMA en az 1 aydır pozitif eğimli
            if not self.check_sma_uptrend(df, period=200, days=30):
                return None
            
            # Kriter 3: IBD RS > 85
            rs_rank = self.calculate_ibd_rs(df, sp500_data)
            if rs_rank is None or rs_rank < rs_threshold:
                return None
            
            # Kriter 4: VCP Base tespit
            vcp_base = self.detect_vcp_base(df)
            if not vcp_base:
                return None
            
            # Pivot ve mesafe
            pivot, distance = self.find_pivot_point(df)
            
            # Hacim spike kontrolü
            volume_spike, spike_ratio = self.check_volume_spike(df)
            
            # Stop-loss
            stop_loss = self.calculate_stop_loss(current_price)
            
            # Durum
            status = self.determine_status(current_price, pivot, distance, vcp_base, spike_ratio)
            
            # JSON formatında sonuç
            result = {
                "ticker": ticker,
                "market": "US",
                "status": status,
                "current_price": round(current_price, 2),
                "pivot_price": pivot,
                "distance_to_pivot_pct": distance,
                "stop_loss": stop_loss,
                "rs_rank": rs_rank,
                "sma_50": round(sma_50, 2),
                "sma_150": round(sma_150, 2),
                "sma_200": round(sma_200, 2),
                "vcp_details": {
                    "pullback_from_high_pct": vcp_base['pullback_pct'],
                    "is_tight": vcp_base['is_tight'],
                    "last_volatility_pct": vcp_base['last_volatility'],
                    "volume_decreasing": vcp_base['volume_decreasing']
                },
                "volume_spike_ratio": spike_ratio,
                "scan_timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            return None
    
    def scan_bist_stock_cross_check(self, ticker, xu100_data, rs_threshold=1.2):
        """BIST hissesi tara - TL ve USD grafik cross-check"""
        try:
            # TL bazlı (Yahoo Finance: TICKER.IS)
            ticker_tl = f"{ticker}.IS"
            stock_tl = yf.Ticker(ticker_tl)
            df_tl = stock_tl.history(period="1y")
            
            if len(df_tl) < 200:
                return None
            
            # USD bazlı için USDTRY kuru çek
            usdtry = yf.Ticker("USDTRY=X")
            df_usd_rate = usdtry.history(period="1y")
            
            if len(df_usd_rate) < 200:
                return None
            
            # TL fiyatları USD'ye çevir
            df_usd = df_tl.copy()
            
            # Tarihleri eşleştir
            df_usd = df_usd.join(df_usd_rate[['Close']], rsuffix='_USDTRY', how='inner')
            df_usd['Close'] = df_tl['Close'] / df_usd['Close_USDTRY']
            df_usd['High'] = df_tl['High'] / df_usd['Close_USDTRY']
            df_usd['Low'] = df_tl['Low'] / df_usd['Close_USDTRY']
            
            if len(df_usd) < 200:
                return None
            
            # TL grafik kontrolü
            tl_result = self._check_stage2_bist(df_tl, xu100_data, rs_threshold)
            
            # USD grafik kontrolü
            usd_result = self._check_stage2_bist(df_usd, xu100_data, rs_threshold)
            
            # Her iki grafik de Aşama 2'de mi?
            if not (tl_result and usd_result):
                return None
            
            # TL bazlı ana hesaplamalar
            current_price_tl = df_tl['Close'].iloc[-1]
            current_price_usd = df_usd['Close'].iloc[-1]
            
            pivot_tl, distance_tl = self.find_pivot_point(df_tl)
            stop_loss_tl = self.calculate_stop_loss(current_price_tl)
            
            volume_spike, spike_ratio = self.check_volume_spike(df_tl)
            
            vcp_base = self.detect_vcp_base(df_tl)
            if not vcp_base:
                return None
            
            status = self.determine_status(current_price_tl, pivot_tl, distance_tl, vcp_base, spike_ratio)
            
            # JSON formatında sonuç
            result = {
                "ticker": ticker,
                "market": "BIST",
                "status": status,
                "current_price_tl": round(current_price_tl, 2),
                "current_price_usd": round(current_price_usd, 2),
                "pivot_price": pivot_tl,
                "distance_to_pivot_pct": distance_tl,
                "stop_loss": stop_loss_tl,
                "rs_rank": tl_result['rs_correlation'],
                "sma_50_tl": round(tl_result['sma_50'], 2),
                "sma_150_tl": round(tl_result['sma_150'], 2),
                "sma_200_tl": round(tl_result['sma_200'], 2),
                "cross_check": {
                    "tl_stage2": True,
                    "usd_stage2": True,
                    "both_confirmed": True
                },
                "vcp_details": {
                    "pullback_from_high_pct": vcp_base['pullback_pct'],
                    "is_tight": vcp_base['is_tight'],
                    "last_volatility_pct": vcp_base['last_volatility'],
                    "volume_decreasing": vcp_base['volume_decreasing']
                },
                "volume_spike_ratio": spike_ratio,
                "scan_timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            return None
    
    def _check_stage2_bist(self, df, xu100_data, rs_threshold):
        """BIST için Aşama 2 kontrolü (yardımcı fonksiyon)"""
        try:
            if len(df) < 200:
                return None
            
            current_price = df['Close'].iloc[-1]
            sma_150 = self.calculate_sma(df, 150).iloc[-1]
            sma_200 = self.calculate_sma(df, 200).iloc[-1]
            sma_50 = self.calculate_sma(df, 50).iloc[-1]
            
            # NaN kontrolü
            if pd.isna(sma_150) or pd.isna(sma_200) or pd.isna(sma_50):
                return None
            
            # Aşama 2 kriterleri
            if not (current_price > sma_150 and current_price > sma_200):
                return None
            
            if not self.check_sma_uptrend(df, period=200, days=30):
                return None
            
            # RS korelasyon
            rs_correlation = self.calculate_bist_rs_correlation(df, xu100_data)
            if rs_correlation is None or rs_correlation < rs_threshold:
                return None
            
            return {
                'sma_50': sma_50,
                'sma_150': sma_150,
                'sma_200': sma_200,
                'rs_correlation': rs_correlation
            }
            
        except:
            return None
    
    def save_results_json(self, filename="sepa_scan_results.json"):
        """Sonuçları JSON dosyasına kaydet"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"\n✓ JSON sonuçları kaydedildi: {filename}")
            return filename
        except Exception as e:
            print(f"✗ JSON kaydetme hatası: {e}")
            return None
    
    def print_json_results(self):
        """Sonuçları JSON formatında yazdır"""
        print("\n" + "=" * 80)
        print("JSON FORMATLI SONUÇLAR")
        print("=" * 80)
        print(json.dumps(self.results, indent=2, ensure_ascii=False))
        print("=" * 80)
    
    def run_sepa_scan(self, us_tickers, bist_tickers):
        """SEPA taraması başlat"""
        print("=" * 80)
        print("MARK MINERVINI SEPA METODOLOJISI - PROFESYONEL TARAMA")
        print("Trend Template 2.0 + VCP + JSON Sinyal Üretimi")
        print("=" * 80)
        
        # Pazar verileri
        print("\n📊 Pazar verileri yükleniyor...")
        sp500 = yf.Ticker("^GSPC").history(period="1y")
        xu100 = yf.Ticker("XU100.IS").history(period="1y")
        print("✓ S&P 500 ve XU100 verileri yüklendi")
        
        # ABD Taraması
        print(f"\n🇺🇸 ABD Taraması: {len(us_tickers)} hisse (RS > 85)")
        for i, ticker in enumerate(us_tickers, 1):
            print(f"[{i}/{len(us_tickers)}] {ticker} taranıyor...", end='\r')
            result = self.scan_us_stock(ticker, sp500, rs_threshold=85)
            if result:
                self.results.append(result)
        
        print(f"\n✓ ABD: {len([r for r in self.results if r['market'] == 'US'])} hisse bulundu")
        
        # BIST Taraması (TL/USD Cross-Check)
        print(f"\n🇹🇷 BIST Taraması: {len(bist_tickers)} hisse (TL/USD Cross-Check)")
        for i, ticker in enumerate(bist_tickers, 1):
            print(f"[{i}/{len(bist_tickers)}] {ticker} taranıyor...", end='\r')
            result = self.scan_bist_stock_cross_check(ticker, xu100, rs_threshold=1.2)
            if result:
                self.results.append(result)
        
        print(f"\n✓ BIST: {len([r for r in self.results if r['market'] == 'BIST'])} hisse bulundu")
        
        # Özet
        print("\n" + "=" * 80)
        print(f"🎯 TOPLAM {len(self.results)} HİSSE KRİTERLERİ KARŞILIYOR")
        print("=" * 80)
        
        # Duruma göre grupla
        breakouts = [r for r in self.results if r['status'] == 'BREAKOUT']
        pivot_touch = [r for r in self.results if r['status'] == 'PIVOT_TOUCH']
        setups = [r for r in self.results if r['status'] == 'SETUP']
        
        if breakouts:
            print(f"\n🚀 BREAKOUT: {len(breakouts)} hisse")
            for r in breakouts:
                flag = "🇺🇸" if r['market'] == 'US' else "🇹🇷"
                price_key = 'current_price' if r['market'] == 'US' else 'current_price_tl'
                currency = "$" if r['market'] == 'US' else "₺"
                print(f"   {flag} {r['ticker']} - {currency}{r.get(price_key, r.get('current_price_tl', 0)):.2f} | RS: {r['rs_rank']}")
        
        if pivot_touch:
            print(f"\n⭐ PIVOT_TOUCH: {len(pivot_touch)} hisse")
            for r in pivot_touch:
                flag = "🇺🇸" if r['market'] == 'US' else "🇹🇷"
                price_key = 'current_price' if r['market'] == 'US' else 'current_price_tl'
                currency = "$" if r['market'] == 'US' else "₺"
                print(f"   {flag} {r['ticker']} - {currency}{r.get(price_key, r.get('current_price_tl', 0)):.2f} | Pivot: {currency}{r['pivot_price']:.2f}")
        
        if setups:
            print(f"\n📊 SETUP: {len(setups)} hisse")
            for r in setups[:5]:  # İlk 5
                flag = "🇺🇸" if r['market'] == 'US' else "🇹🇷"
                print(f"   {flag} {r['ticker']} - VCP Tight: {r['vcp_details']['is_tight']}")
        
        # JSON kaydet
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file = f"sepa_scan_{timestamp}.json"
        self.save_results_json(json_file)
        
        return self.results

def main():
    scanner = SEPAScanner()
    
    # Örnek hisse listeleri (gerçek kullanımda genişletin)
    us_tickers = [
        'AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'META', 'TSLA', 'AMZN',
        'LRCX', 'AMAT', 'KLAC', 'RTX', 'LMT', 'CAT', 'GE', 'BA',
        'JPM', 'BAC', 'GS', 'MS', 'V', 'MA', 'CRWD', 'PANW'
    ]
    
    bist_tickers = [
        'AKBNK', 'GARAN', 'ISCTR', 'YKBNK', 'THYAO', 'TUPRS',
        'KCHOL', 'SAHOL', 'EREGL', 'ASELS', 'SISE', 'PETKM'
    ]
    
    results = scanner.run_sepa_scan(us_tickers, bist_tickers)
    
    print("\n💡 JSON formatında sonuçlar API/webhook entegrasyonu için hazır!")
    print(f"   Dosya: sepa_scan_*.json")

if __name__ == "__main__":
    main()

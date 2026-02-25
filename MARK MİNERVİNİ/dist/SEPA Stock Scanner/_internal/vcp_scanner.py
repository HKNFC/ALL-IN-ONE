#!/usr/bin/env python3
"""
VCP (Volatility Contraction Pattern) Tarayıcı
Mark Minervini'nin VCP metodolojisine göre hisse analizi
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def calculate_volatility(prices):
    """Fiyat volatilitesini hesapla (yüzde olarak)"""
    if len(prices) < 2:
        return 0
    high = prices.max()
    low = prices.min()
    return ((high - low) / low) * 100

def detect_contractions(df, weeks=4):
    """Daralmalarını tespit et"""
    contractions = []
    
    # Son weeks haftalık veriyi al
    cutoff_date = df.index[-1] - timedelta(weeks=weeks)
    recent_df = df[df.index >= cutoff_date].copy()
    
    if len(recent_df) < weeks * 3:  # Minimum 3 gün/hafta
        return []
    
    # Her haftayı analiz et
    weeks_data = []
    for i in range(weeks):
        start_date = recent_df.index[-1] - timedelta(weeks=weeks-i)
        end_date = recent_df.index[-1] - timedelta(weeks=weeks-i-1)
        week_data = recent_df[(recent_df.index >= start_date) & (recent_df.index < end_date)]
        
        if len(week_data) > 0:
            volatility = calculate_volatility(week_data['Close'])
            avg_volume = week_data['Volume'].mean()
            weeks_data.append({
                'week': i + 1,
                'volatility': volatility,
                'avg_volume': avg_volume,
                'high': week_data['Close'].max(),
                'low': week_data['Close'].min()
            })
    
    # Daralmalarını tespit et (volatilite düşüşü)
    for i in range(1, len(weeks_data)):
        if weeks_data[i]['volatility'] < weeks_data[i-1]['volatility']:
            contractions.append({
                'week': weeks_data[i]['week'],
                'volatility': weeks_data[i]['volatility'],
                'prev_volatility': weeks_data[i-1]['volatility'],
                'volume_decreased': weeks_data[i]['avg_volume'] < weeks_data[i-1]['avg_volume']
            })
    
    return contractions

def calculate_pivot_distance(df):
    """Pivot noktasına (direnç hattı) uzaklığı hesapla"""
    # Son 4-8 haftalık en yüksek = pivot
    lookback_period = min(60, len(df))  # 60 gün (~3 ay)
    recent_data = df.tail(lookback_period)
    pivot = recent_data['Close'].max()
    current_price = df['Close'].iloc[-1]
    distance = ((pivot - current_price) / pivot) * 100
    return pivot, distance

def check_volume_dryup(df, days=5):
    """Son N günde hacim kurumayı kontrol et"""
    if len(df) < days + 5:
        return False, None
    
    last_n_days = df.tail(days)
    prev_n_days = df.tail(days * 2).head(days)
    
    avg_volume_last = last_n_days['Volume'].mean()
    avg_volume_prev = prev_n_days['Volume'].mean()
    
    volume_decrease_pct = ((avg_volume_prev - avg_volume_last) / avg_volume_prev) * 100
    
    # Hacim en az %10 düşmüşse "kurudu" say
    return volume_decrease_pct > 10, volume_decrease_pct

def analyze_vcp(ticker):
    """VCP analizi yap"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo")  # 6 aylık veri
        
        if len(df) < 60:  # Minimum 60 günlük veri gerekli
            return None
        
        # Daralmalarını tespit et
        contractions = detect_contractions(df, weeks=4)
        
        # En az 2 daralma olmalı
        if len(contractions) < 2:
            return None
        
        # Hacim düşüşü olan daralmalar
        volume_decreased_count = sum(1 for c in contractions if c['volume_decreased'])
        
        # Pivot mesafesi
        pivot, pivot_distance = calculate_pivot_distance(df)
        
        # Hacim kuruma kontrolü
        volume_dryup, volume_decrease_pct = check_volume_dryup(df, days=5)
        
        current_price = df['Close'].iloc[-1]
        
        # VCP Tightness: Pivot'a %2'den yakın VE son 5 günde hacim kurudu
        is_buy_radar = (pivot_distance <= 2.0) and volume_dryup
        
        # Son 5 günlük volatilite
        last_5_days_volatility = calculate_volatility(df['Close'].tail(5))
        
        return {
            'Ticker': ticker,
            'Fiyat': round(current_price, 2),
            'Daralma_Sayısı': len(contractions),
            'Hacim_Düşen_Daralma': volume_decreased_count,
            'Pivot': round(pivot, 2),
            'Pivot_Uzaklık_%': round(pivot_distance, 2),
            'Son_5Gün_Volatilite_%': round(last_5_days_volatility, 2),
            'Hacim_Kuruma_%': round(volume_decrease_pct, 2) if volume_decrease_pct else 0,
            'Alım_Radarı': '⭐ EVET' if is_buy_radar else 'Hayır'
        }
        
    except Exception as e:
        return None

def scan_vcp_from_csv(csv_file):
    """CSV dosyasından hisseleri okuyup VCP analizi yap"""
    try:
        df = pd.read_csv(csv_file)
        tickers = df['Ticker'].tolist()
        return tickers
    except Exception as e:
        print(f"CSV okuma hatası: {e}")
        return []

def main():
    print("=" * 100)
    print("VCP (Volatility Contraction Pattern) Tarayıcı - Mark Minervini Metodolojisi")
    print("=" * 100)
    
    # En son Minervini sonuç dosyasını bul
    import glob
    csv_files = glob.glob("minervini_results_*.csv")
    
    if not csv_files:
        print("\n❌ Önce Mark Minervini Trend Template taramasını çalıştırın!")
        print("Komut: python3 minervini_scanner.py")
        return
    
    # En son dosyayı al
    latest_csv = sorted(csv_files)[-1]
    print(f"\n📂 Kaynak dosya: {latest_csv}")
    
    tickers = scan_vcp_from_csv(latest_csv)
    print(f"📊 {len(tickers)} hisse VCP için analiz ediliyor...\n")
    
    results = []
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {ticker} VCP analizi yapılıyor...", end='\r')
        result = analyze_vcp(ticker)
        if result:
            results.append(result)
    
    print("\n" + "=" * 100)
    
    if results:
        df_results = pd.DataFrame(results)
        
        # Alım radarı olanları ayır
        buy_radar = df_results[df_results['Alım_Radarı'] == '⭐ EVET'].copy()
        others = df_results[df_results['Alım_Radarı'] != '⭐ EVET'].copy()
        
        # Sıralama: Önce pivot uzaklığına göre, sonra daralma sayısına göre
        if len(buy_radar) > 0:
            buy_radar = buy_radar.sort_values(['Pivot_Uzaklık_%', 'Daralma_Sayısı'], 
                                              ascending=[True, False])
        
        if len(others) > 0:
            others = others.sort_values(['Daralma_Sayısı', 'Pivot_Uzaklık_%'], 
                                       ascending=[False, True])
        
        print(f"\n✓ TOPLAM {len(df_results)} HİSSEDE VCP TESPİT EDİLDİ\n")
        
        if len(buy_radar) > 0:
            print("=" * 100)
            print(f"🎯 ALIM RADARI - Pivot'a Çok Yakın ve Hacim Kuruyan Hisseler ({len(buy_radar)} adet)")
            print("=" * 100)
            print("Bu hisseler breakout için hazır ve yakın takip edilmeli!\n")
            print(buy_radar.to_string(index=False))
            print("\n")
        
        if len(others) > 0:
            print("=" * 100)
            print(f"📈 DİĞER VCP HİSSELERİ - İzlenmeye Değer ({len(others)} adet)")
            print("=" * 100)
            print(others.to_string(index=False))
            print("\n")
        
        # Detaylı açıklama
        print("=" * 100)
        print("📊 KRİTER AÇIKLAMALARI:")
        print("=" * 100)
        print("• Daralma Sayısı: Son 4 haftada tespit edilen volatilite daralmalarının sayısı (min 2)")
        print("• Hacim Düşen Daralma: Hacmin de düştüğü daralma sayısı (ideal olarak tüm daralmalar)")
        print("• Pivot Uzaklık: Mevcut fiyatın pivot noktasına (direnç) yüzde uzaklığı")
        print("• Son 5 Gün Volatilite: Son 5 günlük fiyat dalgalanması (düşük değer = sıkışma)")
        print("• Hacim Kuruma: Son 5 günde önceki 5 güne göre hacim azalması yüzdesi")
        print("• Alım Radarı: Pivot'a %2'den yakın + Son 5 günde hacim kuruyan hisseler")
        print("\n⚠️  ÖNEMLİ: Breakout anını yakalamak için bu hisseleri günlük takip edin!")
        print("          Pivot seviyesini hacimle geçtiğinde alım sinyali oluşur.")
        print("=" * 100)
        
        # CSV olarak kaydet
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if len(buy_radar) > 0:
            buy_radar_file = f"vcp_buy_radar_{timestamp}.csv"
            buy_radar.to_csv(buy_radar_file, index=False, encoding='utf-8-sig')
            print(f"\n✓ Alım Radarı kaydedildi: {buy_radar_file}")
        
        all_vcp_file = f"vcp_all_results_{timestamp}.csv"
        df_results.to_csv(all_vcp_file, index=False, encoding='utf-8-sig')
        print(f"✓ Tüm VCP sonuçları kaydedildi: {all_vcp_file}")
        
    else:
        print("\n⚠ VCP kriterleri karşılayan hisse bulunamadı.")
        print("   (En az 2 daralma ve yeterli veri gereklidir)")
    
    print()

if __name__ == "__main__":
    main()

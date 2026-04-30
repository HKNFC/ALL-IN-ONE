#!/usr/bin/env python3
"""
Mark Minervini Trend Template Hisse Tarayıcı
Bu script, Mark Minervini'nin Trend Template kriterlerine uyan hisseleri tarar.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def calculate_moving_averages(df):
    """Hareketli ortalamaları hesapla"""
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['SMA_150'] = df['Close'].rolling(window=150).mean()
    df['SMA_200'] = df['Close'].rolling(window=200).mean()
    return df

def calculate_52_week_high_low(df):
    """52 haftalık en yüksek ve en düşük değerleri hesapla"""
    df['52W_High'] = df['Close'].rolling(window=252).max()
    df['52W_Low'] = df['Close'].rolling(window=252).min()
    return df

def check_200sma_uptrend(df, days=21):
    """200 günlük SMA'nın en az 1 aydır yukarı eğilimli olup olmadığını kontrol et"""
    if len(df) < 200 + days:
        return False
    sma_200_now = df['SMA_200'].iloc[-1]
    sma_200_month_ago = df['SMA_200'].iloc[-days]
    return sma_200_now > sma_200_month_ago

def calculate_relative_strength(ticker_data, market_data):
    """Relative Strength (RS) hesapla - S&P 500'e göre"""
    try:
        ticker_return = (ticker_data['Close'].iloc[-1] / ticker_data['Close'].iloc[-252] - 1) * 100
        market_return = (market_data['Close'].iloc[-1] / market_data['Close'].iloc[-252] - 1) * 100
        rs = ((1 + ticker_return/100) / (1 + market_return/100) - 1) * 100 + 50
        return max(0, min(100, rs))
    except:
        return None

def check_minervini_criteria(ticker, market_data):
    """Mark Minervini Trend Template kriterlerini kontrol et"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y")
        
        if len(df) < 252:
            return None
        
        df = calculate_moving_averages(df)
        df = calculate_52_week_high_low(df)
        
        latest = df.iloc[-1]
        current_price = latest['Close']
        sma_50 = latest['SMA_50']
        sma_150 = latest['SMA_150']
        sma_200 = latest['SMA_200']
        high_52w = latest['52W_High']
        low_52w = latest['52W_Low']
        
        if pd.isna(sma_50) or pd.isna(sma_150) or pd.isna(sma_200):
            return None
        
        criteria = {}
        
        # Kriter 1: Mevcut fiyat > 150 ve 200 günlük SMA
        criteria['price_above_150_200'] = current_price > sma_150 and current_price > sma_200
        
        # Kriter 2: 150 günlük SMA > 200 günlük SMA
        criteria['sma_150_above_200'] = sma_150 > sma_200
        
        # Kriter 3: 200 günlük SMA en az 1 aydır yukarı eğilimli
        criteria['sma_200_uptrend'] = check_200sma_uptrend(df)
        
        # Kriter 4: 50 günlük SMA > 150 ve 200 günlük SMA
        criteria['sma_50_above_150_200'] = sma_50 > sma_150 and sma_50 > sma_200
        
        # Kriter 5: Mevcut fiyat, 52 haftalık en düşükten en az %25 yukarıda
        criteria['price_25_above_low'] = current_price >= low_52w * 1.25
        
        # Kriter 6: Mevcut fiyat, 52 haftalık en yükseğe %25 veya daha yakın
        criteria['price_near_high'] = current_price >= high_52w * 0.75
        
        # RS Hesaplama
        rs = calculate_relative_strength(df, market_data)
        criteria['rs'] = rs
        
        # Tüm kriterleri karşılıyor mu?
        all_criteria_met = all([
            criteria['price_above_150_200'],
            criteria['sma_150_above_200'],
            criteria['sma_200_uptrend'],
            criteria['sma_50_above_150_200'],
            criteria['price_25_above_low'],
            criteria['price_near_high']
        ])
        
        if all_criteria_met:
            return {
                'Ticker': ticker,
                'Fiyat': round(current_price, 2),
                'SMA_50': round(sma_50, 2),
                'SMA_150': round(sma_150, 2),
                'SMA_200': round(sma_200, 2),
                '52W_High': round(high_52w, 2),
                '52W_Low': round(low_52w, 2),
                'High_dan_Uzaklık_%': round(((high_52w - current_price) / high_52w) * 100, 2),
                'Low_dan_Artış_%': round(((current_price - low_52w) / low_52w) * 100, 2),
                'RS': round(rs, 2) if rs else 'N/A'
            }
        
        return None
        
    except Exception as e:
        return None

def scan_stocks(tickers):
    """Hisse listesini tara"""
    print("Mark Minervini Trend Template Tarayıcı")
    print("=" * 80)
    print(f"Taranan hisse sayısı: {len(tickers)}")
    print("Tarama başlıyor...\n")
    
    # S&P 500 verilerini al (pazar karşılaştırması için)
    market_data = yf.Ticker("^GSPC").history(period="2y")
    
    results = []
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {ticker} taranıyor...", end='\r')
        result = check_minervini_criteria(ticker, market_data)
        if result:
            results.append(result)
    
    print("\n" + "=" * 80)
    
    if results:
        df_results = pd.DataFrame(results)
        
        # RS değerine göre sırala (yüksekten düşüğe)
        df_results['RS_numeric'] = pd.to_numeric(df_results['RS'], errors='coerce')
        df_results = df_results.sort_values('RS_numeric', ascending=False)
        df_results = df_results.drop('RS_numeric', axis=1)
        
        # RS > 70 olanları vurgula
        print(f"\n✓ TOPLAM {len(df_results)} HİSSE TREND TEMPLATE KRİTERLERİNİ KARŞILIYOR\n")
        
        high_rs = df_results[pd.to_numeric(df_results['RS'], errors='coerce') > 70]
        if len(high_rs) > 0:
            print(f"★ RS > 70 OLAN ÖNCELİKLİ HİSSELER ({len(high_rs)} adet):")
            print("=" * 80)
            print(high_rs.to_string(index=False))
            print("\n")
        
        if len(df_results) > len(high_rs):
            print(f"DİĞER HİSSELER ({len(df_results) - len(high_rs)} adet):")
            print("=" * 80)
            other_rs = df_results[pd.to_numeric(df_results['RS'], errors='coerce') <= 70]
            print(other_rs.to_string(index=False))
        
        # CSV olarak kaydet
        filename = f"minervini_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df_results.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✓ Sonuçlar kaydedildi: {filename}")
        
    else:
        print("\n⚠ Kriterleri karşılayan hisse bulunamadı.")
    
    return results

if __name__ == "__main__":
    # S&P 500 hisselerinden örnekler (geniş tarama için liste genişletilebilir)
    # Amerikan hisse senetleri
    us_tickers = [
        # Teknoloji
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'NFLX', 'AMD', 'CRM',
        'ADBE', 'INTC', 'CSCO', 'ORCL', 'AVGO', 'QCOM', 'TXN', 'AMAT', 'LRCX', 'KLAC',
        'SHOP', 'SQ', 'SNOW', 'PLTR', 'DDOG', 'CRWD', 'ZS', 'NET', 'OKTA', 'PANW',
        
        # Sağlık
        'UNH', 'JNJ', 'PFE', 'ABBV', 'TMO', 'MRK', 'ABT', 'DHR', 'BMY', 'LLY',
        'AMGN', 'GILD', 'CVS', 'ISRG', 'VRTX', 'REGN', 'MRNA', 'ZTS', 'BIIB', 'ILMN',
        
        # Finans
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'USB',
        'PNC', 'TFC', 'COF', 'BK', 'STT', 'V', 'MA', 'PYPL',
        
        # Tüketim
        'AMZN', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'LOW', 'TJX', 'COST', 'WMT',
        'DIS', 'CMCSA', 'CHTR', 'NFLX', 'SONY', 'BKNG', 'MAR', 'HLT',
        
        # Sanayi
        'BA', 'CAT', 'HON', 'UPS', 'UNP', 'RTX', 'LMT', 'GE', 'MMM', 'DE',
        'FDX', 'DAL', 'AAL', 'UAL', 'LUV',
        
        # Enerji
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL',
        
        # Popüler büyüme hisseleri
        'COIN', 'RBLX', 'UBER', 'LYFT', 'ABNB', 'DASH', 'RIVN', 'LCID', 'NIO', 'XPEV',
        'ROKU', 'PINS', 'SNAP', 'TWLO', 'ZM', 'DOCU', 'PTON', 'TDOC'
    ]
    
    # Listeyi benzersiz hale getir
    us_tickers = list(set(us_tickers))
    
    print(f"\nToplam {len(us_tickers)} hisse taranacak...\n")
    
    scan_stocks(us_tickers)

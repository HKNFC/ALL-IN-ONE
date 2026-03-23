#!/usr/bin/env python3
"""
Birleşik BIST + ABD Borsası Tarayıcı
Mark Minervini Evrensel Trend Filtresi ve VCP Analizi
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import logging

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# Twelvedata birincil kaynak, yoksa Yahoo Finance fallback
try:
    import twelvedata_client as td
    _TD_AVAILABLE = True
except Exception:
    _TD_AVAILABLE = False
logging.getLogger('urllib3').setLevel(logging.CRITICAL)
logging.getLogger('peewee').setLevel(logging.CRITICAL)

class UniversalStockScanner:
    """BIST ve ABD borsaları için birleşik tarayıcı"""
    
    def __init__(self):
        self.us_tickers = self.get_us_tickers()
        self.bist_tickers = self.get_bist_tickers()
    
    def get_us_tickers(self):
        """S&P500 + NASDAQ — Twelvedata (birincil) → Wikipedia (fallback)"""
        # Twelvedata
        if _TD_AVAILABLE:
            tickers = td.get_us_tickers()
            if len(tickers) > 100:
                return tickers

        # Wikipedia fallback
        try:
            import requests
            from bs4 import BeautifulSoup
            tickers = set()
            r = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                headers={'User-Agent': 'Mozilla/5.0'}, timeout=15
            )
            soup = BeautifulSoup(r.content, 'html.parser')
            table = soup.find('table', {'id': 'constituents'})
            if table:
                for row in table.find_all('tr')[1:]:
                    cells = row.find_all('td')
                    if cells:
                        sym = cells[0].text.strip().replace('.', '-')
                        if sym:
                            tickers.add(sym)
            if len(tickers) > 100:
                result = sorted(tickers)
                print(f"🇺🇸 Wikipedia S&P500: {len(result)} hisse yüklendi!")
                return result
        except Exception:
            pass

        # Son çare: sabit liste
        print("⚠️ US fallback listesi kullanılıyor (101 hisse)...")
        return [
            'AAPL','MSFT','GOOGL','AMZN','META','NVDA','TSLA','NFLX','AMD','CRM',
            'ADBE','INTC','CSCO','ORCL','AVGO','QCOM','TXN','AMAT','LRCX','KLAC',
            'SHOP','SNOW','PLTR','DDOG','CRWD','ZS','NET','OKTA','PANW','FTNT',
            'UNH','JNJ','PFE','ABBV','TMO','MRK','ABT','DHR','BMY','LLY',
            'AMGN','GILD','CVS','ISRG','VRTX','REGN','MRNA','ZTS','BIIB','ILMN',
            'JPM','BAC','WFC','GS','MS','C','BLK','SCHW','AXP','USB',
            'PNC','TFC','COF','BK','STT','V','MA','PYPL',
            'HD','NKE','MCD','SBUX','TGT','LOW','TJX','COST','WMT','BKNG',
            'MAR','HLT','DIS','CMCSA','CHTR',
            'BA','CAT','HON','UPS','UNP','RTX','LMT','GE','MMM','DE',
            'XOM','CVX','COP','SLB','EOG','MPC','PSX','VLO','OXY','HAL',
            'COIN','UBER','ABNB','RIVN','NIO','ROKU','SNAP','ZM','SOFI','AFRM',
        ]
    
    def get_bist_tickers(self):
        """BIST TÜM hisse listesi — Twelvedata (birincil) → KAP → hardcoded fallback"""
        # Twelvedata (628 hisse)
        if _TD_AVAILABLE:
            tickers = td.get_bist_tickers()
            if len(tickers) > 100:
                return tickers

        # KAP fallback
        try:
            import requests
            from bs4 import BeautifulSoup
            
            print("🔄 BIST hisseleri güncelleniyor...")
            
            # BIST 100 listesini çek
            url = "https://www.kap.org.tr/tr/bist-sirketler"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Tüm BIST şirket kodlarını çek
                tickers = []
                for row in soup.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) > 0:
                        code = cells[0].text.strip()
                        if code and len(code) <= 6 and code.isalpha():
                            tickers.append(code)
                
                if len(tickers) > 100:
                    print(f"✅ {len(tickers)} BIST hissesi bulundu!")
                    return [f"{code}.IS" for code in tickers]
            except:
                pass
            
            # Fallback: Genişletilmiş manuel liste (500+ hisse)
            print("⚠️ Otomatik çekme başarısız, genişletilmiş liste kullanılıyor...")
            
            bist_codes = [
                # BIST 30
                'AKBNK', 'ARCLK', 'ASELS', 'BIMAS', 'EKGYO', 'ENJSA', 'EREGL', 'GARAN',
                'GUBRF', 'HALKB', 'ISCTR', 'KCHOL', 'KOZAL', 'KOZAA', 'KRDMD', 'PETKM',
                'PGSUS', 'SAHOL', 'SASA', 'SISE', 'TAVHL', 'TCELL', 'THYAO', 'TOASO',
                'TTKOM', 'TUPRS', 'VAKBN', 'VESTL', 'YKBNK', 'EREGL',
                
                # BIST 50 Ek
                'AEFES', 'AFYON', 'AKSA', 'ALARK', 'ALBRK', 'ALCTL', 'ALGYO', 'ANACM',
                'AYGAZ', 'BAGFS', 'BRSAN', 'CCOLA', 'CIMSA', 'DOAS', 'DOHOL', 'EGEEN',
                'ENKAI', 'FROTO', 'GENTS', 'GLYHO', 'GOZDE', 'HEKTS', 'IEYHO', 'IPEKE',
                'ISCTR', 'ISGYO', 'KARSN', 'KLMSN', 'KONTR', 'KONYA', 'KORDS', 'LOGO',
                'MAVI', 'MGROS', 'ODAS', 'OTKAR', 'OYAKC', 'PARKL', 'PARSN', 'PENGD',
                
                # BIST 100 Ek
                'ADEL', 'ADESE', 'AEFES', 'AGHOL', 'AGROT', 'AGYO', 'AHGAZ', 'AKCNS',
                'AKENR', 'AKFGY', 'AKFYE', 'AKGRT', 'AKMGY', 'AKSA', 'AKSEN', 'AKSGY',
                'AKSUE', 'AKYHO', 'ALARK', 'ALBRK', 'ALCAR', 'ALCTL', 'ALFAS', 'ALGYO',
                'ALKA', 'ALKIM', 'ALMAD', 'ALTIN', 'ALTNY', 'ANELE', 'ANGEN', 'ANHYT',
                'ANSGR', 'ARASE', 'ARCLK', 'ARDYZ', 'ARENA', 'ARSAN', 'ARTMS', 'ARZUM',
                'ASELS', 'ASGYO', 'ASTOR', 'ASUZU', 'ATAGY', 'ATAKP', 'ATATP', 'ATEKS',
                'ATLAS', 'ATSYH', 'AVGYO', 'AVHOL', 'AVOD', 'AVPGY', 'AVTUR', 'AYCES',
                'AYDEM', 'AYEN', 'AYGAZ', 'AZTEK', 'BAGFS', 'BAHKM', 'BAKAB', 'BALAT',
                
                # Yeni Eklenenler
                'BANVT', 'BARMA', 'BASCM', 'BASGZ', 'BAYRK', 'BEGYO', 'BERA', 'BEYAZ',
                'BFREN', 'BIGCH', 'BIMAS', 'BIOEN', 'BIZIM', 'BJKAS', 'BLCYT', 'BMSCH',
                'BMSTL', 'BNTAS', 'BOBET', 'BORLS', 'BORSK', 'BOSSA', 'BRISA', 'BRKO',
                'BRKSN', 'BRKVY', 'BRLSM', 'BRMEN', 'BRSAN', 'BRYAT', 'BSOKE', 'BTCIM',
                'BUCIM', 'BURCE', 'BURVA', 'BVSAN', 'BYDNR', 'CANTE', 'CASA', 'CATES',
                'CCOLA', 'CELHA', 'CEMAS', 'CEMTS', 'CEMZY', 'CEOEM', 'CIMSA', 'CLEBI',
                'CMBTN', 'CMENT', 'CONSE', 'COSMO', 'CRDFA', 'CRFSA', 'CUSAN', 'CVKMD',
                'CWENE', 'DAGHL', 'DAGI', 'DAPGM', 'DARDL', 'DCTTR', 'DENIZ', 'DERHL',
                'DERIM', 'DESA', 'DESPC', 'DEVA', 'DGATE', 'DGGYO', 'DGNMO', 'DIRIT',
                
                # Teknoloji & Yazılım
                'ESCOM', 'INDES', 'KAREL', 'LINK', 'LOGO', 'NETAS', 'PKART', 'SMART',
                'VESBE', 'VKING',
                
                # E-ticaret & Dijital
                'MAVI', 'MPARK', 'PENTA', 'SARKY', 'TKNSA', 'UFUK',
                
                # Enerji & Elektrik
                'AKENR', 'AKSUE', 'AKSEN', 'AYDEM', 'ENERG', 'GENIL', 'GWIND', 'HUNER',
                'MAGEN', 'ODAS', 'RTALB', 'TLMAN', 'TRCAS', 'ZOREN',
                
                # Gayrimenkul
                'AGYO', 'ALGYO', 'AVGYO', 'DGGYO', 'EKGYO', 'ISGYO', 'OZGYO', 'OZKGY',
                'PAGYO', 'PEGYO', 'RYGYO', 'SRVGY', 'TRGYO', 'VKGYO', 'YKGYO',
                
                # Gıda & İçecek
                'AEFES', 'BANVT', 'CCOLA', 'ERSU', 'KNFRT', 'KERVT', 'PENGD', 'PETUN',
                'PINSU', 'TATGD', 'TUKAS', 'ULKER', 'VANGD',
                
                # İnşaat & Altyapı
                'EDIP', 'ENKAI', 'EPLAS', 'EUREN', 'FENKS', 'FMIZP', 'GOLTS', 'GUSGR',
                'IZFAS', 'IZINV', 'KALER', 'KLSER', 'KUTPO', 'MAALT', 'MAKTK', 'MARTI',
                'MEPET', 'MERIT', 'MERKO', 'METRO', 'MHRGY', 'MNDRS', 'MNDTR', 'MPARK',
                
                # Sanayi
                'DOBUR', 'DOGUB', 'DOHOL', 'DOKTA', 'DURDO', 'DYOBY', 'EDATA', 'EGEPO',
                'EGPRO', 'EGSER', 'EGGUB', 'EMKEL', 'EMNIS', 'ENJSA', 'ENKAI', 'ENSRI',
                'EPLAS', 'ERBOS', 'ERCB', 'EREGL', 'ERSU', 'ESCAR', 'ESCOM', 'ESEN',
                'ETILR', 'ETYAT', 'EUKYO', 'EUREN', 'EURO', 'EUYO', 'EYGYO', 'FADE',
                
                # Turizm & Otelcilik
                'AVTUR', 'AYCES', 'DNISI', 'ETILR', 'MAALT', 'MARTI', 'MERIT', 'PKENT',
                'RTALB', 'SANFM', 'SEYKM', 'SNGYO', 'TEKTU', 'ULAS', 'UTPYA',
                
                # Tekstil & Deri
                'BLCYT', 'BRKO', 'BRMEN', 'DERIM', 'DESA', 'HATEK', 'IDAS', 'KRTEK',
                'LUKSK', 'MAVI', 'MNTAL', 'RODRG', 'SKTAS', 'SNPAM', 'SONME', 'SUMAS',
                'YUNSA',
                
                # Madencilik & Metal
                'ANELT', 'ASLAN', 'BASCM', 'BURCE', 'BURVA', 'CEMAS', 'CEMTS', 'CUSAN',
                'DOKTA', 'ERBOS', 'EREGL', 'ERMAN', 'ERTIT', 'FENER', 'GEREL', 'GOLTS',
                'GUBRE', 'IHEVA', 'IHGZT', 'IHLGM', 'INTEM', 'IZMDC', 'IZTAR', 'JANTS',
                'KAPLM', 'KARTN', 'KENT', 'KLKIM', 'KLSER', 'KLSYN', 'KMPUR', 'KRSTL',
                
                # Lojistik & Taşımacılık
                'BEYAZ', 'BINHO', 'CLEBI', 'GSDHO', 'PRKAB', 'RYSAS', 'THYAO', 'TLMAN',
                'TMSN', 'TSGYO', 'TURGG', 'ULAS', 'VANGD',
                
                # İletişim
                'ANELE', 'ARENA', 'ASELS', 'ATSYH', 'BFREN', 'BIGCH', 'KAREL', 'NETAS',
                'TCELL', 'TTKOM', 'TTRAK', 'TUREX',
                
                # Diğer Sektörler
                'SELEC', 'SISE', 'SKBNK', 'SKYLF', 'SMRTG', 'SNGYO', 'SOKE', 'SOKM',
                'SRVGY', 'SUWEN', 'TATGD', 'TAVHL', 'TBORG', 'TCELL', 'TEZOL', 'TGSAS',
                'TIRE', 'TKFEN', 'TKNSA', 'TMPOL', 'TOASO', 'TRGYO', 'TRILC', 'TSPOR',
                'TTKOM', 'TTRAK', 'TUCLK', 'TUKAS', 'TUREX', 'TURGG', 'TURSG', 'UFUK',
                'ULKER', 'ULUFA', 'ULUUN', 'UMPAS', 'UNLU', 'USAK', 'UTPYA', 'VAKBN',
                'VAKFN', 'VAKKO', 'VANGD', 'VERTU', 'VERUS', 'VESBE', 'VESTL', 'VKFYO',
                'VKGYO', 'VKING', 'YAPRK', 'YATAS', 'YAYLA', 'YEOTK', 'YESIL', 'YGGYO',
                'YGYO', 'YKBNK', 'YKSLN', 'YUNSA', 'YYAPI', 'ZEDUR', 'ZELOT', 'ZOREN', 'ZRGYO'
            ]
            
            # Yahoo Finance için .IS uzantısı ekle — tekrar edenleri temizle
            unique_codes = list(dict.fromkeys(bist_codes))
            print(f"✅ {len(unique_codes)} BIST hissesi yüklendi!")
            return [f"{code}.IS" for code in unique_codes]
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            # Minimal fallback
            return ['AKBNK.IS', 'GARAN.IS', 'ISCTR.IS', 'YKBNK.IS', 'THYAO.IS', 'TUPRS.IS']
    
    def calculate_sma(self, df, period):
        """SMA hesapla"""
        return df['Close'].rolling(window=period).mean()

    def _compute_indicators(self, df):
        """Tüm teknik göstergeleri tek geçişte vektörel hesapla.
        Her hisse için ayrı ayrı rolling çağrısı yapmak yerine
        pandas C-level vektörizasyonu ile ~3x hızlanma sağlar."""
        c = df['Close']
        ind = {}
        ind['sma_50']  = c.rolling(50,  min_periods=50).mean()
        ind['sma_150'] = c.rolling(150, min_periods=150).mean()
        ind['sma_200'] = c.rolling(200, min_periods=200).mean()
        ind['high_52w'] = c.rolling(252, min_periods=20).max()
        ind['low_52w']  = c.rolling(252, min_periods=20).min()
        ind['pct_chg']  = c.pct_change()
        # Son değerleri float olarak al
        def last(s):
            v = s.iloc[-1]
            return float(v.iloc[0]) if isinstance(v, pd.Series) else float(v)
        ind['price']    = last(c)
        ind['sma50_v']  = last(ind['sma_50'])
        ind['sma150_v'] = last(ind['sma_150'])
        ind['sma200_v'] = last(ind['sma_200'])
        ind['high52_v'] = last(ind['high_52w'])
        ind['low52_v']  = last(ind['low_52w'])
        # 200G SMA 30 gün önce (uptrend kontrolü)
        if len(ind['sma_200'].dropna()) >= 30:
            v = ind['sma_200'].iloc[-30]
            ind['sma200_past'] = float(v.iloc[0]) if isinstance(v, pd.Series) else float(v)
        else:
            ind['sma200_past'] = ind['sma200_v']
        return ind

    def check_sma_uptrend(self, df, period=200, days=30):
        """SMA'nın yukarı eğilimli olup olmadığını kontrol et"""
        if len(df) < period + days:
            return False
        sma = self.calculate_sma(df, period)
        sma_now  = sma.iloc[-1]
        sma_past = sma.iloc[-days]
        if isinstance(sma_now,  pd.Series): sma_now  = float(sma_now.iloc[0])
        if isinstance(sma_past, pd.Series): sma_past = float(sma_past.iloc[0])
        return sma_now > sma_past
    
    def calculate_rs_us(self, stock_df, market_df):
        """
        ABD için RS hesapla — hissenin S&P500'e göre bağıl fazla getirisi (%).

        ⚠️  KRİTİK KURAL — DEĞİŞTİRME:
        - Sonuç normalize EDİLMEZ, 0-100 arasına KISITLANMAZ.
        - Ham bağıl getiri değeri korunur (örn: MU=316, CIEN=167, FIX=134).
        - Bu değer backtest ve scanner'da RS sıralaması için kullanılır.
        - Değeri kırparsanız (min/max/normalize) tüm güçlü hisseler aynı skoru
          alır ve sıralama rastgele olur → backtest/scanner sonuçları tutarsızlaşır.
        """
        try:
            if len(stock_df) < 252 or len(market_df) < 252:
                return None
            
            # Son 1 yıllık performans
            stock_close_now = stock_df['Close'].iloc[-1]
            stock_close_past = stock_df['Close'].iloc[-252]
            market_close_now = market_df['Close'].iloc[-1]
            market_close_past = market_df['Close'].iloc[-252]
            
            # pandas Series dönerse float'a çevir
            if isinstance(stock_close_now, pd.Series):
                stock_close_now = float(stock_close_now.iloc[0]) if len(stock_close_now) > 0 else float(stock_close_now)
            if isinstance(stock_close_past, pd.Series):
                stock_close_past = float(stock_close_past.iloc[0]) if len(stock_close_past) > 0 else float(stock_close_past)
            if isinstance(market_close_now, pd.Series):
                market_close_now = float(market_close_now.iloc[0]) if len(market_close_now) > 0 else float(market_close_now)
            if isinstance(market_close_past, pd.Series):
                market_close_past = float(market_close_past.iloc[0]) if len(market_close_past) > 0 else float(market_close_past)
            
            stock_return = (stock_close_now / stock_close_past - 1) * 100
            market_return = (market_close_now / market_close_past - 1) * 100
            
            # RS: hissenin S&P500'e göre bağıl fazla getirisi
            # Cap yok — gerçek ayrışma değeri korunur (sıralama için kritik)
            rs = ((1 + stock_return/100) / (1 + market_return/100) - 1) * 100
            return round(rs, 2)
        except Exception as e:
            return None
    
    def calculate_rs_bist(self, stock_df, xu100_df):
        """BIST için RS - son 3 ayda XU100'e göre performans"""
        try:
            if len(stock_df) < 63 or len(xu100_df) < 63:  # ~3 ay
                return None
            
            stock_close_now = stock_df['Close'].iloc[-1]
            stock_close_past = stock_df['Close'].iloc[-63]
            xu100_close_now = xu100_df['Close'].iloc[-1]
            xu100_close_past = xu100_df['Close'].iloc[-63]
            
            # pandas Series dönerse float'a çevir
            if isinstance(stock_close_now, pd.Series):
                stock_close_now = float(stock_close_now.iloc[0]) if len(stock_close_now) > 0 else float(stock_close_now)
            if isinstance(stock_close_past, pd.Series):
                stock_close_past = float(stock_close_past.iloc[0]) if len(stock_close_past) > 0 else float(stock_close_past)
            if isinstance(xu100_close_now, pd.Series):
                xu100_close_now = float(xu100_close_now.iloc[0]) if len(xu100_close_now) > 0 else float(xu100_close_now)
            if isinstance(xu100_close_past, pd.Series):
                xu100_close_past = float(xu100_close_past.iloc[0]) if len(xu100_close_past) > 0 else float(xu100_close_past)
            
            stock_return = (stock_close_now / stock_close_past - 1) * 100
            xu100_return = (xu100_close_now / xu100_close_past - 1) * 100
            
            # Pozitif ayrışma: Hisse > Endeks
            divergence = stock_return - xu100_return
            return divergence
        except Exception as e:
            return None
    
    def detect_vcp_pattern(self, df):
        """VCP (Volatility Contraction Pattern) tespit et"""
        if len(df) < 70:  # ~10 hafta = 70 gün
            return None
        
        # Son 10 haftalık veriyi al
        recent = df.tail(70)
        
        # Her haftayı analiz et (yaklaşık 5 günlük bloklar)
        weeks = []
        for i in range(10):
            start_idx = i * 7
            end_idx = start_idx + 7
            week_data = recent.iloc[start_idx:end_idx]
            
            if len(week_data) > 0:
                high = week_data['High'].max()
                low = week_data['Low'].min()
                
                # pandas Series dönerse float'a çevir
                if isinstance(high, pd.Series):
                    high = float(high.iloc[0]) if len(high) > 0 else float(high)
                if isinstance(low, pd.Series):
                    low = float(low.iloc[0]) if len(low) > 0 else float(low)
                
                volatility = ((high - low) / low) * 100
                weeks.append(volatility)
        
        if len(weeks) < 3:
            return None
        
        # İlk 3 haftada %30 -> %10 -> %3 gibi bir daralma var mı?
        # Basit kontrol: ardışık volatilite düşüşleri
        contractions = 0
        for i in range(len(weeks) - 1):
            if weeks[i+1] < weeks[i]:
                contractions += 1
        
        # En az 2 daralma ve son hafta %3'ün altında
        if contractions >= 2 and weeks[-1] < 3.0:
            return {
                'contractions': contractions,
                'last_week_volatility': weeks[-1],
                'pattern': 'TIGHT'
            }
        elif contractions >= 2 and weeks[-1] < 10.0:
            return {
                'contractions': contractions,
                'last_week_volatility': weeks[-1],
                'pattern': 'FORMING'
            }
        
        return None
    
    def find_pivot_point(self, df):
        """Pivot noktası (20 günlük en yüksek) tespit et"""
        if len(df) < 20:
            return None, None
        
        last_20_days = df.tail(20)
        pivot = last_20_days['High'].max()
        current_price = df['Close'].iloc[-1]
        
        # pandas Series dönerse float'a çevir
        if isinstance(pivot, pd.Series):
            pivot = float(pivot.iloc[0]) if len(pivot) > 0 else float(pivot)
        if isinstance(current_price, pd.Series):
            current_price = float(current_price.iloc[0]) if len(current_price) > 0 else float(current_price)
        
        distance_to_pivot = ((pivot - current_price) / pivot) * 100
        
        return pivot, distance_to_pivot
    
    def check_volume_dryup_us(self, df):
        """ABD için hacim kuruması: son 50 günlük ortalamanın %50 altı"""
        if len(df) < 50:
            return False, None
        
        avg_volume_50 = df['Volume'].tail(50).mean()
        last_5_volume = df['Volume'].tail(5).mean()
        
        # pandas Series dönerse float'a çevir
        if isinstance(avg_volume_50, pd.Series):
            avg_volume_50 = float(avg_volume_50.iloc[0]) if len(avg_volume_50) > 0 else float(avg_volume_50)
        if isinstance(last_5_volume, pd.Series):
            last_5_volume = float(last_5_volume.iloc[0]) if len(last_5_volume) > 0 else float(last_5_volume)
        
        ratio = (last_5_volume / avg_volume_50)
        
        # %50 altındaysa hacim kurudu
        return ratio < 0.5, ratio * 100
    
    def check_volume_spike(self, df):
        """Hacim artışı (Volume Spike > %50) kontrolü"""
        if len(df) < 20:
            return False, None
        
        avg_volume = df['Volume'].tail(20).mean()
        current_volume = df['Volume'].iloc[-1]
        
        # pandas Series dönerse float'a çevir
        if isinstance(avg_volume, pd.Series):
            avg_volume = float(avg_volume.iloc[0]) if len(avg_volume) > 0 else float(avg_volume)
        if isinstance(current_volume, pd.Series):
            current_volume = float(current_volume.iloc[0]) if len(current_volume) > 0 else float(current_volume)
        
        spike_ratio = (current_volume / avg_volume)
        
        return spike_ratio > 1.5, spike_ratio
    
    def determine_status(self, distance_to_pivot, vcp_pattern, volume_spike_ratio):
        """Hisse durumunu belirle"""
        if distance_to_pivot is None:
            return "INSUFFICIENT_DATA"
        
        # BREAKOUT: Pivot'u hacimli kırdı
        if distance_to_pivot < 0 and volume_spike_ratio and volume_spike_ratio > 1.5:
            return "BREAKOUT"
        
        # PIVOT_NEAR: Pivot'a %1'den yakın ve VCP var
        if 0 <= distance_to_pivot <= 1.0 and vcp_pattern:
            return "PIVOT_NEAR"
        
        # SETUP: VCP var ama pivot'tan uzak
        if vcp_pattern and distance_to_pivot <= 5.0:
            return "SETUP"
        
        return "WATCHING"

    # ------------------------------------------------------------------
    # Endeks / Pazar Listesi Metotları
    # ------------------------------------------------------------------

    def get_bist100_tickers(self):
        """BIST 100 endeksi hisseleri"""
        codes = [
            'AKBNK','ARCLK','ASELS','BIMAS','EKGYO','ENJSA','EREGL','FROTO','GARAN','GUBRF',
            'HALKB','ISCTR','KCHOL','KONTR','KOZAA','KOZAL','KRDMD','PETKM','PGSUS','SAHOL',
            'SASA','SISE','TAVHL','TCELL','THYAO','TOASO','TTKOM','TTRAK','TUPRS','VAKBN',
            'VESTL','YKBNK','AEFES','AGHOL','AGESA','AKSA','AKSEN','ALARK','AYGAZ','BAGFS',
            'BRSAN','CCOLA','CIMSA','DOAS','DOHOL','ENKAI','GLYHO','HEKTS','ISGYO','KARSN',
            'KLMSN','LOGO','MGROS','MPARK','NTHOL','ODAS','OTKAR','OYAKC','SELEC','SKBNK',
            'SOKM','SMRTG','TSKB','ULKER','ZOREN','AKGRT','ALBRK','ANSGR','ANHYT','ASUZU',
            'AVOD','AYEN','BRISA','EGEEN','GENTS','HLGYO','INDES','IPEKE','KLGYO','MAVI',
            'NUHCM','PKART','POLHO','SANFM','TEKTU','TKNSA','TMPOL','TRGYO','TURSG','VKGYO',
        ]
        return [f"{c}.IS" for c in dict.fromkeys(codes)]

    def get_bist_xutum_tickers(self):
        """BIST XUTUM — Tüm Şirketler Endeksi (Ana Pazar)"""
        return self.bist_tickers

    def get_bist_xtumy_tickers(self):
        """BIST XTUMY — Yıldız Pazar Endeksi"""
        codes = [
            'AKBNK','ARCLK','ASELS','BIMAS','EKGYO','ENJSA','EREGL','FROTO','GARAN','GUBRF',
            'HALKB','ISCTR','KCHOL','KONTR','KOZAA','KOZAL','KRDMD','PETKM','PGSUS','SAHOL',
            'SASA','SISE','TAVHL','TCELL','THYAO','TOASO','TTKOM','TUPRS','VAKBN','YKBNK',
            'AEFES','AGHOL','AKSA','AKSEN','ALARK','AYGAZ','BRSAN','CCOLA','CIMSA','DOHOL',
            'ENKAI','HEKTS','ISGYO','KARSN','LOGO','MGROS','MPARK','ODAS','OTKAR','OYAKC',
            'SOKM','TSKB','ULKER','ZOREN','AKGRT','ANHYT','ASUZU','AVOD','BAGFS','BRISA',
            'DOAS','EGEEN','GENTS','HLGYO','INDES','MAVI','NUHCM','PKART','POLHO','SANFM',
            'TKNSA','TRGYO','TURSG','VKGYO','AGESA','ALBRK','ANSGR','KLGYO','NTHOL','SELEC',
        ]
        return [f"{c}.IS" for c in dict.fromkeys(codes)]

    def get_tickers_by_scan_type(self, scan_type, manual_list=None):
        """scan_type'a göre doğru ticker listesini döndür"""
        if scan_type == 'BIST100':
            return self.get_bist100_tickers()
        elif scan_type == 'BISTXUTUM':
            return self.get_bist_xutum_tickers()
        elif scan_type == 'BISTXTUMY':
            return self.get_bist_xtumy_tickers()
        elif scan_type == 'BISTMANUEL':
            if manual_list:
                tickers = []
                for t in manual_list:
                    t = t.strip().upper()
                    if t:
                        tickers.append(t if t.endswith('.IS') else f"{t}.IS")
                return tickers
            return []
        else:  # 'BISTTUM' veya default
            return self.bist_tickers

    def scan_us_stock(self, ticker, sp500_data, stock_data=None, as_of_date=None):
        """ABD hissesi tara (backtest için stock_data opsiyonel, as_of_date geçmiş tarama için)"""
        try:
            if stock_data is None:
                df = self._fetch_ohlcv(ticker, as_of_date)
            else:
                df = stock_data

            if len(df) < 200:
                return None

            ind = self._compute_indicators(df)
            current_price = ind['price']
            sma_150 = ind['sma150_v']
            sma_200 = ind['sma200_v']

            # Kriter 1: Fiyat > 150G ve 200G SMA
            if not (current_price > sma_150 and current_price > sma_200):
                return None

            # Kriter 2: 200G SMA 30 gündür yukarı eğilimli
            if ind['sma200_v'] <= ind['sma200_past']:
                return None

            # RS Hesapla (IBD tarzı - GEVŞETİLDİ: 80 -> 70)
            rs = self.calculate_rs_us(df, sp500_data)
            if rs is None:
                rs = 50  # RS hesaplanamazsa orta değer

            # VCP tespit et (OPSİYONEL - yoksa da devam et)
            vcp_pattern = self.detect_vcp_pattern(df)
            if not vcp_pattern:
                vcp_pattern = {
                    'contractions': 0,
                    'last_week_volatility': 0,
                    'pattern': 'NO_VCP'
                }

            # Pivot ve mesafe
            pivot, distance_to_pivot = self.find_pivot_point(df)

            # Hacim kontrolü
            volume_dryup, volume_ratio = self.check_volume_dryup_us(df)
            volume_spike, spike_ratio = self.check_volume_spike(df)

            # Durum belirle
            status = self.determine_status(distance_to_pivot, vcp_pattern, spike_ratio)

            # Stop level
            stop_level = current_price * 0.93  # %7 altı

            return {
                'Market': 'US',
                'Ticker': ticker,
                'Price': round(current_price, 2),
                'SMA_150': round(sma_150, 2),
                'SMA_200': round(sma_200, 2),
                'RS': round(rs, 2),
                'VCP_Contractions': int(vcp_pattern['contractions']),
                'VCP_Pattern': vcp_pattern['pattern'],
                'Pivot': round(pivot, 2) if pivot else None,
                'Distance_to_Pivot_%': round(distance_to_pivot, 2) if distance_to_pivot else None,
                'Volume_Dryup': bool(volume_dryup),  # NumPy bool -> Python bool
                'Status': status,
                'Stop_Level': round(stop_level, 2),
                'Volume_Spike_Ratio': round(spike_ratio, 2) if spike_ratio else None
            }
            
        except Exception as e:
            return None
    
    def _fetch_ohlcv(self, ticker, as_of_date=None):
        """
        Twelvedata (birincil) → Yahoo Finance (fallback) ile OHLCV çek.
        as_of_date: geçmiş tarih taraması için; None = bugün
        """
        cutoff = pd.Timestamp(as_of_date).normalize() if as_of_date else pd.Timestamp.today().normalize()
        start  = (cutoff - timedelta(days=420)).strftime('%Y-%m-%d')
        end    = (cutoff + timedelta(days=1)).strftime('%Y-%m-%d')

        if _TD_AVAILABLE:
            df = td.get_time_series(ticker, start, end)
            if not df.empty and len(df) >= 50:
                return df[df.index.normalize() <= cutoff]

        # Yahoo Finance fallback
        import io, contextlib
        yf_sym = ticker if not ticker.endswith('.IS') else ticker
        with contextlib.redirect_stderr(io.StringIO()), \
             contextlib.redirect_stdout(io.StringIO()):
            if as_of_date:
                raw = yf.download(yf_sym, start=start, end=end,
                                  auto_adjust=True, progress=False)
            else:
                raw = yf.Ticker(yf_sym).history(period='1y')
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return raw[raw.index.normalize() <= cutoff] if as_of_date else raw


    def scan_bist_stock(self, ticker, xu100_data, stock_data=None, as_of_date=None):
        """BIST hissesi tara (backtest için stock_data opsiyonel, as_of_date geçmiş tarama için)"""
        try:
            if stock_data is None:
                df = self._fetch_ohlcv(ticker, as_of_date)
            else:
                # Backtest için önceden çekilmiş veriyi kullan
                df = stock_data
            
            if len(df) < 200:
                return None

            ind = self._compute_indicators(df)
            current_price = ind['price']
            sma_150 = ind['sma150_v']
            sma_200 = ind['sma200_v']

            # Kriter 1: Fiyat > 150G ve 200G SMA
            if not (current_price > sma_150 and current_price > sma_200):
                return None

            # Kriter 2: 200G SMA 30 gündür yukarı eğilimli
            if ind['sma200_v'] <= ind['sma200_past']:
                return None

            # RS Hesapla (XU100'e göre pozitif ayrışma)
            # GEVŞETME: Negatif RS'yi kabul et, ama bildirmek için hesapla
            rs_divergence = self.calculate_rs_bist(df, xu100_data)
            if rs_divergence is None:
                rs_divergence = 0  # RS hesaplanamazsa 0 olarak işaretle

            # VCP tespit et (OPSİYONEL - yoksa da devam et)
            vcp_pattern = self.detect_vcp_pattern(df)
            # VCP yoksa default değerler
            if not vcp_pattern:
                vcp_pattern = {
                    'contractions': 0,
                    'last_week_volatility': 0,
                    'pattern': 'NO_VCP'
                }

            # Pivot ve mesafe
            pivot, distance_to_pivot = self.find_pivot_point(df)

            # Hacim kontrolü
            volume_spike, spike_ratio = self.check_volume_spike(df)

            # Durum belirle
            status = self.determine_status(distance_to_pivot, vcp_pattern, spike_ratio)

            # Stop level
            stop_level = current_price * 0.93  # %7 altı

            # Ticker'dan .IS'i kaldır
            clean_ticker = ticker.replace('.IS', '')
            
            return {
                'Market': 'BIST',
                'Ticker': clean_ticker,
                'Price': round(current_price, 2),
                'SMA_150': round(sma_150, 2),
                'SMA_200': round(sma_200, 2),
                'RS_Divergence_%': round(rs_divergence, 2),
                'VCP_Contractions': int(vcp_pattern['contractions']),
                'VCP_Pattern': vcp_pattern['pattern'],
                'Pivot': round(pivot, 2) if pivot else None,
                'Distance_to_Pivot_%': round(distance_to_pivot, 2) if distance_to_pivot else None,
                'Status': status,
                'Stop_Level': round(stop_level, 2),
                'Volume_Spike_Ratio': round(spike_ratio, 2) if spike_ratio else None
            }
            
        except Exception as e:
            return None
    
    def run_universal_scan(self):
        """Birleşik tarama başlat"""
        print("=" * 100)
        print("EVRENSEL BORSA TARAYICI - Mark Minervini Metodolojisi")
        print("BIST (Borsa İstanbul) + ABD Borsaları (NYSE, NASDAQ)")
        print("=" * 100)
        
        # Pazar verilerini çek
        print("\n📊 Pazar verileri yükleniyor...")
        sp500 = yf.Ticker("^GSPC").history(period="1y")
        xu100 = yf.Ticker("XU100.IS").history(period="1y")
        print("✓ S&P 500 ve XU100 verileri yüklendi\n")
        
        # ABD Taraması
        print(f"🇺🇸 ABD Borsaları: {len(self.us_tickers)} hisse taranıyor...")
        us_results = []
        for i, ticker in enumerate(self.us_tickers, 1):
            print(f"[US {i}/{len(self.us_tickers)}] {ticker} taranıyor...", end='\r')
            result = self.scan_us_stock(ticker, sp500)
            if result:
                us_results.append(result)
        
        print(f"\n✓ ABD taraması tamamlandı: {len(us_results)} aday bulundu\n")
        
        # BIST Taraması
        print(f"🇹🇷 BIST: {len(self.bist_tickers)} hisse taranıyor...")
        bist_results = []
        for i, ticker in enumerate(self.bist_tickers, 1):
            print(f"[BIST {i}/{len(self.bist_tickers)}] {ticker} taranıyor...", end='\r')
            result = self.scan_bist_stock(ticker, xu100)
            if result:
                bist_results.append(result)
        
        print(f"\n✓ BIST taraması tamamlandı: {len(bist_results)} aday bulundu\n")
        
        # Sonuçları birleştir
        all_results = us_results + bist_results
        
        if not all_results:
            print("⚠ Kriterleri karşılayan hisse bulunamadı.")
            return
        
        df_results = pd.DataFrame(all_results)
        
        # Duruma göre sırala
        status_order = {'BREAKOUT': 1, 'PIVOT_NEAR': 2, 'SETUP': 3, 'WATCHING': 4}
        df_results['Status_Order'] = df_results['Status'].map(status_order)
        df_results = df_results.sort_values(['Status_Order', 'Market', 'Distance_to_Pivot_%'])
        df_results = df_results.drop('Status_Order', axis=1)
        
        # Durumlara göre ayır
        breakouts = df_results[df_results['Status'] == 'BREAKOUT']
        pivot_near = df_results[df_results['Status'] == 'PIVOT_NEAR']
        setups = df_results[df_results['Status'] == 'SETUP']
        watching = df_results[df_results['Status'] == 'WATCHING']
        
        print("=" * 100)
        print(f"🎯 TOPLAM {len(df_results)} HİSSE KRİTERLERİ KARŞILIYOR")
        print("=" * 100)
        
        if len(breakouts) > 0:
            print(f"\n🚀 BREAKOUT - Pivot'u Hacimli Kırdı ({len(breakouts)} adet)")
            print("=" * 100)
            self.print_results(breakouts)
        
        if len(pivot_near) > 0:
            print(f"\n⭐ PIVOT_NEAR - Alım Noktasına Çok Yakın ({len(pivot_near)} adet)")
            print("=" * 100)
            self.print_results(pivot_near)
        
        if len(setups) > 0:
            print(f"\n📊 SETUP - VCP Oluşumu Devam Ediyor ({len(setups)} adet)")
            print("=" * 100)
            self.print_results(setups)
        
        if len(watching) > 0:
            print(f"\n👀 WATCHING - İzlenmeye Değer ({len(watching)} adet)")
            print("=" * 100)
            self.print_results(watching)
        
        # Açıklamalar
        self.print_explanations()
        
        # Kaydet
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"universal_scan_{timestamp}.csv"
        df_results.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✓ Sonuçlar kaydedildi: {filename}")
        
        # Breakout watchlist kaydet
        if len(breakouts) > 0 or len(pivot_near) > 0:
            watchlist = pd.concat([breakouts, pivot_near])
            watchlist_file = f"breakout_watchlist_{timestamp}.csv"
            watchlist.to_csv(watchlist_file, index=False, encoding='utf-8-sig')
            print(f"✓ Breakout watchlist kaydedildi: {watchlist_file}")
        
        return df_results
    
    def print_results(self, df):
        """Sonuçları formatla ve yazdır"""
        for _, row in df.iterrows():
            market_flag = "🇺🇸" if row['Market'] == 'US' else "🇹🇷"
            
            if row['Market'] == 'US':
                print(f"{market_flag} US - {row['Ticker']} - {row['Status']}")
                print(f"   Fiyat: ${row['Price']:.2f} | Pivot: ${row['Pivot']:.2f} | Mesafe: {row['Distance_to_Pivot_%']:.2f}%")
                print(f"   RS: {row['RS']:.2f} | VCP: {row['VCP_Contractions']} daralma ({row['VCP_Pattern']})")
                print(f"   Stop: ${row['Stop_Level']:.2f} (-7%)")
            else:
                print(f"{market_flag} BIST - {row['Ticker']} - {row['Status']}")
                print(f"   Fiyat: ₺{row['Price']:.2f} | Pivot: ₺{row['Pivot']:.2f} | Mesafe: {row['Distance_to_Pivot_%']:.2f}%")
                print(f"   RS Ayrışma: +{row['RS_Divergence_%']:.2f}% | VCP: {row['VCP_Contractions']} daralma ({row['VCP_Pattern']})")
                print(f"   Stop: ₺{row['Stop_Level']:.2f} (-7%)")
            
            if row['Volume_Spike_Ratio']:
                print(f"   Hacim: {row['Volume_Spike_Ratio']:.2f}x")
            
            print()
    
    def print_explanations(self):
        """Açıklamalar"""
        print("\n" + "=" * 100)
        print("📖 DURUM AÇIKLAMALARI")
        print("=" * 100)
        print("🚀 BREAKOUT: Pivot seviyesini hacimli kırdı - ALIM SİNYALİ")
        print("⭐ PIVOT_NEAR: Pivot'a %1'den yakın, VCP var - ÇOK YAKIN TAKİP")
        print("📊 SETUP: VCP oluşumu var, pivot'tan biraz uzak - İZLE")
        print("👀 WATCHING: Kriterleri karşılıyor ama henüz erken - RADAR")
        print("\n💡 ÖNERİLER:")
        print("• BREAKOUT hisseler için: Derhal pozisyon al, stop %7 altında")
        print("• PIVOT_NEAR hisseler için: Günlük takip et, hacimli kırılımı bekle")
        print("• Stop-loss: Giriş fiyatının %7 altında katı dur")
        print("=" * 100)

def main():
    scanner = UniversalStockScanner()
    scanner.run_universal_scan()

if __name__ == "__main__":
    main()

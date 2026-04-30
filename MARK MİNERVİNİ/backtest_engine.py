"""
Minervini Backtest Engine v2
============================
Tüm tarihsel veri backtest başında TEK KEZ indirilir, önbelleğe alınır.
Her rebalancing periyodunda veri yeniden indirilmez — hafızadan dilimle kullanılır.

Özellikler:
- Global tek seferlik indirme — çok daha hızlı
- Ticker-tabanlı önbellek (tarih aralığından bağımsız)
- Aylık / 15 günlük / haftalık rebalancing
- RS ve Minervini yöntemleri
"""

import math
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import warnings
import logging
import time
import os
import hashlib
import pickle

# SQLite fiyat DB (deterministik backtest için)
try:
    from stock_db import get_db as _get_stock_db
    _STOCK_DB_AVAILABLE = True
except ImportError:
    _STOCK_DB_AVAILABLE = False

warnings.filterwarnings('ignore')
logging.getLogger('yfinance').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)

from universal_scanner import UniversalStockScanner


def _to_float(val):
    if isinstance(val, pd.Series):
        val = val.iloc[0] if len(val) > 0 else 0.0
    try:
        f = float(val)
        return f if (not math.isnan(f) and not math.isinf(f)) else 0.0
    except Exception:
        return 0.0


class MarketDataCache:
    """
    Ticker başına tam DataFrame saklar.
    Cache key = sadece ticker sembolü.
    get_slice() ile istenen tarih aralığını keserek döndürür.

    Disk cache: indirilen veriler data_cache/ klasörüne kaydedilir.
    Aynı parametrelerle tekrar çalıştırıldığında aynı veri kullanılır
    → backtest sonuçları deterministik (tekrarlanabilir) olur.
    """

    DISK_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_cache')
    CACHE_TTL_DAYS = 90  # 90 gün — geçmiş veri değişmez, her gün yeniden indirmeye gerek yok

    # Proses-level RAM cache — disk'e bile gitmeden aynı oturumda hızlı döner
    _RAM_CACHE: dict = {}

    def __init__(self):
        self._data = {}          # {ticker: DataFrame}
        self._bad  = set()       # veri gelmeyen tickerlar
        os.makedirs(self.DISK_CACHE_DIR, exist_ok=True)

    # ── Disk cache helpers ───────────────────────────────────────────────────

    def _disk_key(self, ticker, start, end):
        raw = f"{ticker}_{str(start)[:10]}_{str(end)[:10]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def _disk_path(self, ticker, start, end):
        return os.path.join(self.DISK_CACHE_DIR, f"{self._disk_key(ticker, start, end)}.pkl")

    def _load_disk(self, ticker, start, end):
        path = self._disk_path(ticker, start, end)
        if not os.path.exists(path):
            return None
        age_days = (time.time() - os.path.getmtime(path)) / 86400
        if age_days > self.CACHE_TTL_DAYS:
            return None
        try:
            with open(path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            return None

    def _save_disk(self, ticker, start, end, df):
        try:
            with open(self._disk_path(ticker, start, end), 'wb') as f:
                pickle.dump(df, f)
            # RAM cache'e de yaz
            ram_key = self._disk_key(ticker, start, end)
            MarketDataCache._RAM_CACHE[ram_key] = df
        except Exception:
            pass

    # ── Temel erişim ──────────────────────────────────────────────────

    def has(self, ticker):
        return ticker in self._data or ticker in self._bad

    def store(self, ticker, df):
        if df is None or df.empty:
            self._bad.add(ticker)
            return
        df = df.sort_index()
        if ticker in self._data and not self._data[ticker].empty:
            combined = pd.concat([self._data[ticker], df])
            combined = combined[~combined.index.duplicated(keep='last')].sort_index()
            self._data[ticker] = combined
        else:
            self._data[ticker] = df

    def get_slice(self, ticker, cutoff=None):
        """Ticker verisini döndürür; cutoff verilmişse o tarihe kadar keser."""
        df = self._data.get(ticker)
        if df is None or df.empty:
            return pd.DataFrame()
        if cutoff is not None:
            df = df[df.index.normalize() <= pd.Timestamp(cutoff).normalize()]
        return df

    # Geriye dönük uyumluluk
    def get(self, ticker, start=None, end=None):
        df = self.get_slice(ticker, end)
        return df if not df.empty else None

    def set(self, ticker, start, end, df):
        self.store(ticker, df)
        if df is not None and not df.empty:
            self._save_disk(ticker, start, end, df)

    def get_or_fetch_disk(self, ticker, start, end):
        """Önce instance cache, sonra RAM cache, sonra SQLite DB, sonra disk cache."""
        if ticker in self._data:
            return self._data[ticker]

        # Proses-level RAM cache — disk I/O olmadan hızlı döner
        ram_key = self._disk_key(ticker, start, end)
        if ram_key in MarketDataCache._RAM_CACHE:
            df = MarketDataCache._RAM_CACHE[ram_key]
            self._data[ticker] = df
            return df

        # ── SQLite DB katmanı (deterministik) ──────────────────────────
        if _STOCK_DB_AVAILABLE:
            try:
                db = _get_stock_db()
                if db.has_data(ticker, min_rows=50):
                    db_df = db.get_prices(ticker, start, end)
                    if db_df is not None and not db_df.empty:
                        self._data[ticker] = db_df
                        MarketDataCache._RAM_CACHE[ram_key] = db_df
                        print(f"  📦 DB'den yüklendi: {ticker} ({len(db_df)} gün)", flush=True)
                        return db_df
            except Exception as _e:
                pass  # DB hatası → disk/live fallback'e devam

        disk_df = self._load_disk(ticker, start, end)
        if disk_df is not None:
            if self._is_stale(ticker, disk_df):
                print(f"  ⚠️  {ticker} cache stale (yanlış fiyat), yeniden indirilecek.", flush=True)
                self._delete_disk(ticker, start, end)
                return None
            self._data[ticker] = disk_df
            MarketDataCache._RAM_CACHE[ram_key] = disk_df  # RAM'e de kaydet
            return disk_df
        return None

    def _is_stale(self, ticker, cached_df):
        """Cache geçerlilik kontrolü — sadece veri boşluğuna bakılır, live fiyat sorgulanmaz.
        Live fiyat kontrolü kaldırıldı: tarife krizi gibi yüksek volatilite dönemlerinde
        historik fiyatlar / anlık fiyat oranı yanlış stale sinyali verebiliyordu."""
        try:
            if cached_df is None or cached_df.empty:
                return True
            if 'Close' not in cached_df.columns:
                return True
            # Veri tutarlılık kontrolü: aşırı NaN oranı varsa stale
            nan_ratio = cached_df['Close'].isna().mean()
            return nan_ratio > 0.5
        except Exception:
            return False

    def _delete_disk(self, ticker, start, end):
        """Bozuk cache dosyasını sil."""
        try:
            path = self._disk_path(ticker, start, end)
            if os.path.exists(path):
                os.remove(path)
                print(f"  🗑️  Stale cache silindi: {os.path.basename(path)}", flush=True)
        except Exception:
            pass

    def get_or_empty(self, ticker, start=None, end=None, cutoff=None):
        return self.get_slice(ticker, cutoff or end)

    # ── Toplu indirme ─────────────────────────────────────────────────

    def bulk_download(self, tickers, start, end, label="hisse"):
        """
        Önbellekte olmayan tickerları TEK SEFERDE toplu indir.
        Önce Twelvedata, kalan eksikler için Yahoo Finance.
        """
        missing = [t for t in tickers if not self.has(t)]
        if not missing:
            print(f"  ✅ Tüm {len(tickers)} {label} zaten önbellekte.", flush=True)
            return

        print(f"  ⬇️  {len(missing)} {label} indiriliyor (toplam {len(tickers)})...", flush=True)

        # ── Twelvedata ──
        td_missing = missing[:]
        try:
            import twelvedata_client as td
            td_results = td.get_batch_time_series(
                td_missing, start, end, batch_size=55, sleep_sec=0.2
            )
            still_missing = []
            for ticker in td_missing:
                df = td_results.get(ticker, pd.DataFrame())
                df = df.dropna(how='all')
                if len(df) >= 5:
                    self.store(ticker, df)
                else:
                    still_missing.append(ticker)
                    self._bad.add(ticker)
            missing = still_missing
        except Exception:
            pass

        if not missing:
            return

        # ── Yahoo Finance fallback ──
        chunk_size = 200
        for i in range(0, len(missing), chunk_size):
            chunk = missing[i:i + chunk_size]
            try:
                import io, contextlib
                with contextlib.redirect_stderr(io.StringIO()), \
                     contextlib.redirect_stdout(io.StringIO()):
                    raw = yf.download(
                        chunk, start=start, end=end,
                        auto_adjust=True, progress=False,
                        threads=True, group_by='ticker',
                    )
            except Exception:
                raw = pd.DataFrame()

            for ticker in chunk:
                try:
                    if len(chunk) == 1:
                        df = raw.copy()
                        if isinstance(df.columns, pd.MultiIndex):
                            # group_by='ticker' ile level-0=ticker, level-1=OHLCV
                            # Her iki düzeni de destekle
                            lvl0 = df.columns.get_level_values(0).tolist()
                            lvl1 = df.columns.get_level_values(1).tolist()
                            if 'Close' in lvl1:
                                df.columns = lvl1
                            elif 'Close' in lvl0:
                                df.columns = lvl0
                            else:
                                df.columns = lvl1
                    else:
                        if isinstance(raw.columns, pd.MultiIndex):
                            lvls = raw.columns.get_level_values(1)
                            if ticker in lvls:
                                df = raw.xs(ticker, axis=1, level=1).copy()
                            else:
                                df = pd.DataFrame()
                        else:
                            df = pd.DataFrame()

                    df = df.dropna(how='all')
                    if len(df) >= 5:
                        self.store(ticker, df)
                    else:
                        self._bad.add(ticker)
                except Exception:
                    self._bad.add(ticker)

            if i + chunk_size < len(missing):
                time.sleep(0.5)

        cached_now = sum(1 for t in tickers if t in self._data)
        print(f"  ✅ {cached_now}/{len(tickers)} {label} önbellekte.", flush=True)


class MinerviniBacktest:
    def __init__(self, start_date, end_date, initial_capital=100000):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.initial_capital = initial_capital
        self.current_capital = float(initial_capital)
        self.scanner = UniversalStockScanner()

        self.portfolio = []
        self.history = []
        self.equity_curve = []

        self._cache = MarketDataCache()
        self._prefetched = False   # global indirme yapıldı mı?

        self._us_tickers = self.scanner.us_tickers

    # ──────────────────────────────────────────────────────────────────
    # Tarih yardımcıları
    # ──────────────────────────────────────────────────────────────────

    def get_first_trading_day_of_month(self, year, month):
        """Ayın ilk iş gününü döndür (Pazar/Cumartesi atlanır)."""
        d = datetime(year, month, 1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d

    def get_rebalance_dates(self, frequency='monthly'):
        dates = []
        current = self.start_date

        if frequency == 'weekly':
            while current <= self.end_date:
                d = current
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                if d <= self.end_date and (not dates or d > dates[-1]):
                    dates.append(d)
                current += timedelta(weeks=1)

        elif frequency == 'biweekly':
            while current <= self.end_date:
                d = current
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                if d <= self.end_date and (not dates or d > dates[-1]):
                    dates.append(d)
                current += timedelta(days=15)

        else:
            # Sabit aralık: başlangıç tarihinden itibaren tam 1'er ay
            while current <= self.end_date:
                d = current
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                if d <= self.end_date:
                    dates.append(d)
                current += relativedelta(months=1)

        return dates

    # ──────────────────────────────────────────────────────────────────
    # Global tek seferlik indirme
    # ──────────────────────────────────────────────────────────────────

    def _global_prefetch(self, tickers, market):
        """
        Backtest başında TÜM veriyi TEK SEFERDE indir.
        fetch_start = start_date - 420 gün (200G SMA için yeterli geçmiş)
        fetch_end   = end_date + 3 gün

        Disk cache: aynı parametrelerle tekrar çalıştırıldığında aynı veri
        kullanılır → backtest sonuçları deterministik (tekrarlanabilir) olur.
        """
        if self._prefetched:
            return

        fetch_start = self.start_date - timedelta(days=420)
        # fetch_end her zaman bugün + 3 gün — scanner ile aynı cache key'i üretir
        # fetch_end: bitiş tarihinden sonraki ilk pazartesiye yuvarla.
        # Böylece aynı backtest parametreleriyle hafta içinde aynı cache key üretilir.
        _raw_end = max(self.end_date.date(), datetime.now().date()) + timedelta(days=3)
        # Haftanın gününe göre en yakın Pazartesiye yuvarla (deterministik key)
        _days_to_monday = (7 - _raw_end.weekday()) % 7
        fetch_end   = _raw_end + timedelta(days=_days_to_monday)
        fetch_end   = pd.Timestamp(fetch_end)

        benchmark    = ['^GSPC', 'XU100.IS', 'SPY']
        all_tickers  = list(dict.fromkeys(tickers + benchmark))

        # DB ve disk cache'den yüklenebilenleri belleğe al
        missing = []
        for t in all_tickers:
            cached = self._cache.get_or_fetch_disk(t, fetch_start, fetch_end)
            if cached is None:
                missing.append(t)

        # DB'de tam verisi olan hisseleri missing listesinden çıkar
        if _STOCK_DB_AVAILABLE:
            try:
                _db = _get_stock_db()
                _db_count = _db.ticker_count()
                if _db_count > 0:
                    missing = [t for t in missing if not _db.has_data(t, min_rows=50)]
                    print(f"   📦 SQLite DB'de {_db_count} hisse var, indirme listesi: {len(missing)}", flush=True)
            except Exception:
                pass

        # ── Bad tickers kalıcı listesini yükle ──────────────────────────
        import json
        _bad_path = os.path.join(self._cache.DISK_CACHE_DIR, 'bad_tickers.json')
        if os.path.exists(_bad_path):
            try:
                with open(_bad_path) as _f:
                    _saved_bad = set(json.load(_f))
                self._cache._bad.update(_saved_bad)
                print(f"   ⚠️  {len(_saved_bad)} kalıcı başarısız hisse yüklendi", flush=True)
            except Exception:
                pass

        if missing:
            print(f"\n📥 Veri indirme başlıyor: {fetch_start.date()} → {fetch_end.date()}", flush=True)
            # Bad ticker listesinden çıkar — zaten başarısız olduğu bilinen hisseleri tekrar deneme
            missing_filtered = [t for t in missing if t not in self._cache._bad]
            print(f"   {len(missing_filtered)} hisse (disk cache'de olmayan, başarısız listede olmayan)", flush=True)
            if missing_filtered:
                # İlk deneme
                self._cache.bulk_download(missing_filtered, fetch_start, fetch_end, label="hisse")
                # Yeni indirilen verileri disk cache'e kaydet
                for t in missing_filtered:
                    df = self._cache.get(t)
                    if df is not None and not df.empty:
                        self._cache._save_disk(t, fetch_start, fetch_end, df)

                # Retry: ilk denemede başarısız olanları tekrar dene
                _still_missing = [t for t in missing_filtered if self._cache.get(t) is None]
                if _still_missing:
                    print(f"   🔄 Retry: {len(_still_missing)} hisse tekrar deneniyor...", flush=True)
                    import time as _time
                    _time.sleep(2)
                    self._cache.bulk_download(_still_missing, fetch_start, fetch_end, label="retry")
                    for t in _still_missing:
                        df = self._cache.get(t)
                        if df is not None and not df.empty:
                            self._cache._save_disk(t, fetch_start, fetch_end, df)

                # Kalıcı olarak başarısız olanları kaydet
                _perm_bad = [t for t in missing_filtered
                             if self._cache.get(t) is None and t not in ('^', 'SPY')]
                if _perm_bad:
                    self._cache._bad.update(_perm_bad)
                    try:
                        _all_bad = list(self._cache._bad - {'^', 'SPY', 'XU100.IS', '^GSPC'})
                        with open(_bad_path, 'w') as _f:
                            json.dump(_all_bad, _f)
                        print(f"   💾 {len(_perm_bad)} başarısız hisse kalıcı listeye eklendi", flush=True)
                    except Exception:
                        pass
        else:
            print(f"\n✅ Tüm veriler disk cache'den yüklendi ({len(all_tickers)} hisse)", flush=True)

        self._prefetched    = True
        self._fetch_start   = fetch_start
        self._fetch_end     = fetch_end

    # ──────────────────────────────────────────────────────────────────
    # Tarama
    # ──────────────────────────────────────────────────────────────────

    def scan_market_at_date(self, scan_date, market='BOTH', tickers_override=None):
        print(f"\n🔍 {scan_date.strftime('%Y-%m-%d')} — {market} taranıyor", flush=True)

        if tickers_override is not None:
            test_tickers = list(tickers_override)
        else:
            bist_tickers = getattr(self.scanner, 'bist_tickers', []) or []
            if market == 'US':
                test_tickers = list(self._us_tickers)
            elif market == 'BIST':
                test_tickers = list(bist_tickers)
            else:
                test_tickers = list(self._us_tickers) + list(bist_tickers)

        # Global indirme yapılmadıysa yap
        if not self._prefetched:
            self._global_prefetch(test_tickers, market)

        cutoff = pd.Timestamp(scan_date).normalize()

        sp500 = self._cache.get_slice('^GSPC', cutoff)
        xu100 = self._cache.get_slice('XU100.IS', cutoff)

        results = []
        passed = failed = 0

        def _score_ticker(ticker):
            stock_data = self._cache.get_slice(ticker, cutoff)
            if len(stock_data) < 200:
                return None
            try:
                is_bist = ticker.endswith('.IS')
                return (
                    self.scanner.scan_bist_stock(ticker, xu100, stock_data)
                    if is_bist
                    else self.scanner.scan_us_stock(ticker, sp500, stock_data)
                )
            except Exception:
                return None

        workers = min(8, max(1, len(test_tickers)))
        sorted_tickers = sorted(test_tickers)  # Deterministik ticker sırası
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {t: pool.submit(_score_ticker, t) for t in sorted_tickers}
            for t in sorted_tickers:  # Sonuçları ticker alfabetik sırasında topla
                try:
                    res = future_map[t].result(timeout=30)
                except Exception:
                    res = None
                if res:
                    results.append(res)
                    passed += 1
                else:
                    failed += 1

        print(f"  ✅ {passed} hisse kriterleri geçti, {failed} geçemedi", flush=True)
        return results

    # ──────────────────────────────────────────────────────────────────
    # Portföy yönetimi
    # ──────────────────────────────────────────────────────────────────

    def select_top_stocks(self, scan_results, top_n=5):
        """
        RS Yöntemi: saf RS skoruna göre sırala.

        ⚠️  KRİTİK KURAL — DEĞİŞTİRME:
        - RS_Score kaynağı: 'RS' (US) veya 'RS_Divergence_%' (BIST) sütunu.
        - Bu değer calculate_rs_us() / calculate_rs_bist() çıktısı — kırpılmamış ham değer.
        - Sıralama: RS_Score azalan → en güçlü bağıl performans gösteren hisse 1. sıraya gelir.
        - Scanner Top Picks butonu da aynı mantığı kullanır (scanner.html: getTopPicks).
        - Backtest ve scanner tutarlılığı bu fonksiyonun değişmemesine bağlıdır.
        """
        priority = [s for s in scan_results if s.get('Status') in ('BREAKOUT', 'PIVOT_NEAR', 'SETUP')]
        if not priority:
            print("  ⚠️ Uygun hisse bulunamadı.", flush=True)
            return []

        df = pd.DataFrame(priority)
        if 'RS' in df.columns:
            df['RS_Score'] = pd.to_numeric(df['RS'], errors='coerce').fillna(0)
        elif 'RS_Divergence_%' in df.columns:
            df['RS_Score'] = pd.to_numeric(df['RS_Divergence_%'], errors='coerce').fillna(0)
        else:
            df['RS_Score'] = 0

        # Deterministik tie-breaking: RS_Score eşitse ticker adına göre sırala
        df = df.sort_values(['RS_Score', 'Ticker'], ascending=[False, True])

        # ── Duplikasyon filtresi: aynı fiyat datasına sahip hisseleri çıkar ──
        selected = []
        seen_prices = set()  # (son_kapanış, son_5_gün_toplam) imzası
        for _, row in df.iterrows():
            ticker = row.get('Ticker', '')
            # Fiyat imzası oluştur
            try:
                stock_df = self._cache.get_slice(ticker, self.end_date)
                if stock_df is not None and len(stock_df) >= 5:
                    sig = (
                        round(float(stock_df['Close'].iloc[-1]), 2),
                        round(float(stock_df['Close'].iloc[-5:].sum()), 2),
                    )
                    if sig in seen_prices:
                        print(f"  ⚠️ {ticker} çıkarıldı: aynı fiyat datasına sahip başka hisse seçildi", flush=True)
                        continue
                    seen_prices.add(sig)
            except Exception:
                pass
            selected.append(row.to_dict())
            if len(selected) >= top_n:
                break
        top = selected

        print(f"  📋 Top {len(top)} hisse (RS Yöntemi):", flush=True)
        for i, s in enumerate(top, 1):
            print(f"    {i}. {s['Ticker']} | RS:{_to_float(s.get('RS_Score',0)):.1f} | {s.get('Status','?')}", flush=True)
        return top

    def select_top_stocks_minervini(self, scan_results, top_n=5):
        """Minervini Yöntemi: kategori önceliği sonra RS"""
        STATUS_PRIORITY = {'BREAKOUT': 3, 'PIVOT_NEAR': 2, 'SETUP': 1}
        priority = [s for s in scan_results if s.get('Status') in STATUS_PRIORITY]
        if not priority:
            print("  ⚠️ Uygun hisse bulunamadı.", flush=True)
            return []

        df = pd.DataFrame(priority)
        if 'RS' in df.columns:
            df['RS_Score'] = pd.to_numeric(df['RS'], errors='coerce').fillna(0)
        elif 'RS_Divergence_%' in df.columns:
            df['RS_Score'] = pd.to_numeric(df['RS_Divergence_%'], errors='coerce').fillna(0)
        else:
            df['RS_Score'] = 0

        df['Status_Priority'] = df['Status'].map(STATUS_PRIORITY).fillna(0)
        df = df.sort_values(['Status_Priority', 'RS_Score'], ascending=[False, False])

        # ── Duplikasyon filtresi ──
        selected = []
        seen_prices = set()
        for _, row in df.iterrows():
            ticker = row.get('Ticker', '')
            try:
                stock_df = self._cache.get_slice(ticker, self.end_date)
                if stock_df is not None and len(stock_df) >= 5:
                    sig = (
                        round(float(stock_df['Close'].iloc[-1]), 2),
                        round(float(stock_df['Close'].iloc[-5:].sum()), 2),
                    )
                    if sig in seen_prices:
                        print(f"  ⚠️ {ticker} çıkarıldı: aynı fiyat datasına sahip başka hisse seçildi", flush=True)
                        continue
                    seen_prices.add(sig)
            except Exception:
                pass
            selected.append(row.to_dict())
            if len(selected) >= top_n:
                break
        top = selected

        print(f"  📋 Top {len(top)} hisse (Minervini):", flush=True)
        for i, s in enumerate(top, 1):
            print(f"    {i}. {s['Ticker']} | RS:{_to_float(s.get('RS_Score',0)):.1f} | {s.get('Status','?')}", flush=True)
        return top

    def _fetch_price_at(self, ticker, date):
        """Belirli tarihteki kapanış fiyatını önbellekten getir. NaN/0 → None döndür."""
        df = self._cache.get_slice(ticker, date)
        if df is not None and not df.empty:
            price = _to_float(df['Close'].iloc[-1])
            if price > 0:
                return price
        return None  # explicit None → or fallback doğru çalışır

    def rebalance_portfolio(self, new_stocks, current_date):
        currency = '₺' if getattr(self, '_market', 'US') == 'BIST' else '$'

        for pos in self.portfolio:
            ticker    = pos['ticker']
            yf_ticker = pos.get('yf_ticker', ticker)
            qty       = pos['quantity']
            entry     = pos['entry_price']

            exit_price = self._fetch_price_at(yf_ticker, current_date)
            if not exit_price or exit_price <= 0:
                exit_price = entry  # fiyat yoksa giriş fiyatıyla kapat (P&L = 0)
                print(f"    ⚠️ {ticker}: fiyat bulunamadı, giriş fiyatı kullanıldı ({currency}{entry:.2f})", flush=True)
            sale_value = qty * exit_price
            self.current_capital += sale_value

            profit     = (exit_price - entry) * qty
            profit_pct = ((exit_price / entry) - 1) * 100 if entry else 0

            self.history.append({
                'date':       current_date.strftime('%Y-%m-%d'),
                'action':     'SELL',
                'ticker':     ticker,
                'quantity':   qty,
                'price':      exit_price,
                'value':      sale_value,
                'profit':     profit,
                'profit_pct': profit_pct,
            })
            print(f"    🔴 SAT: {ticker} {qty} @ {currency}{exit_price:.2f} "
                  f"(P&L: {currency}{profit:.2f} / {profit_pct:.2f}%)", flush=True)

        self.portfolio = []

        if not new_stocks:
            print("  ⚠️ Yeni hisse bulunamadı, nakit bekleniyor.", flush=True)
            return

        capital_per = self.current_capital / len(new_stocks)

        for stock in new_stocks:
            ticker = stock['Ticker']
            market = stock.get('Market', '?')
            price  = _to_float(stock.get('Price', 0))
            if price <= 0:
                continue

            yf_ticker = (ticker + '.IS') if (market == 'BIST' and not ticker.endswith('.IS')) else ticker

            qty = int(capital_per / price)
            if qty == 0:
                continue

            cost = qty * price
            self.current_capital -= cost

            self.portfolio.append({
                'ticker':      ticker,
                'yf_ticker':   yf_ticker,
                'market':      market,
                'quantity':    qty,
                'entry_price': price,
                'entry_date':  current_date.strftime('%Y-%m-%d'),
                'rs_score':    _to_float(stock.get('RS_Score', 0)),
                'status':      stock.get('Status', '?'),
            })
            self.history.append({
                'date':     current_date.strftime('%Y-%m-%d'),
                'action':   'BUY',
                'ticker':   ticker,
                'quantity': qty,
                'price':    price,
                'value':    cost,
            })
            print(f"    🟢 AL: {ticker} {qty} @ {currency}{price:.2f} (Maliyet: {currency}{cost:.2f})", flush=True)

    def calculate_portfolio_value(self, current_date):
        if not self.portfolio:
            return self.current_capital
        total = self.current_capital
        for pos in self.portfolio:
            yf_ticker = pos.get('yf_ticker', pos['ticker'])
            price = self._fetch_price_at(yf_ticker, current_date) or pos['entry_price']
            total += pos['quantity'] * price
        return total

    # ──────────────────────────────────────────────────────────────────
    # Ana backtest döngüsü
    # ──────────────────────────────────────────────────────────────────

    def run_backtest(self, market='BOTH', method='rs', frequency='monthly', engine='classic', portfolio_size=7):
        self._market = market
        self._method = method
        self._frequency = frequency
        self._engine = engine

        currency = '₺' if market == 'BIST' else '$'
        method_label = 'RS Yöntemi' if method == 'rs' else 'Minervini Yöntemi'
        engine_label = ' [Kalibrasyon]' if engine == 'calibrated' else ' [Klasik]'
        freq_labels = {'weekly': 'Haftalık', 'biweekly': '15 Günlük', 'monthly': 'Aylık'}
        freq_label = freq_labels.get(frequency, 'Aylık')

        print("\n" + "=" * 70)
        print(f"🚀 MİNERVİNİ BACKTEST [{method_label}] [{freq_label}]{engine_label}")
        print(f"📅 {self.start_date.date()} → {self.end_date.date()}")
        print(f"💰 Sermaye: {currency}{self.initial_capital:,.0f}  |  Market: {market}")
        print("=" * 70)

        if engine == 'calibrated':
            profile = mcs.get_profile(market)
            print(f"🔧 Market Profile: {profile['name']} | Benchmark: {profile['benchmark']}")
            print(f"   Ağırlıklar: {profile['weights']}")
            print(f"   ROIC: {profile['roic_label']}")

        rebalance_dates = self.get_rebalance_dates(frequency)
        print(f"📆 {len(rebalance_dates)} {freq_label.lower()} rebalancing planlandı")

        # ── TÜM VERİYİ TEK SEFERDE İNDİR ──
        bist_tickers = getattr(self.scanner, 'bist_tickers', []) or []
        if market == 'US':
            all_tickers = list(self._us_tickers)
        elif market == 'BIST':
            all_tickers = list(bist_tickers)
        else:
            all_tickers = list(self._us_tickers) + list(bist_tickers)

        self._global_prefetch(all_tickers, market)

        # ── Rebalancing döngüsü ──
        for i, date in enumerate(rebalance_dates, 1):
            print(f"\n── Periyot {i}/{len(rebalance_dates)}: {date.strftime('%d %B %Y')} ──", flush=True)

            if engine == 'calibrated':
                scan_results = mcs.scan_with_calibration(
                    all_tickers, market,
                    cutoff=pd.Timestamp(date),
                    cache=self._cache
                )
            else:
                scan_results = self.scan_market_at_date(date, market)

            if method == 'minervini':
                top_stocks = self.select_top_stocks_minervini(scan_results, top_n=portfolio_size)
            else:
                top_stocks = self.select_top_stocks(scan_results, top_n=portfolio_size)

            self.rebalance_portfolio(top_stocks, date)

            pv  = float(self.calculate_portfolio_value(date))
            ret = ((pv / self.initial_capital) - 1) * 100
            self.equity_curve.append({
                'date': date.strftime('%Y-%m-%d'),
                'value': pv,
                'return_pct': ret,
            })
            print(f"  💼 Portföy: {currency}{pv:,.2f}  |  Getiri: {ret:+.2f}%", flush=True)

        # ── Final: tüm pozisyonları kapat ──
        print("\n── Final: pozisyonlar kapatılıyor ──", flush=True)
        self.rebalance_portfolio([], self.end_date)

        final_value  = float(self.current_capital)
        total_return = ((final_value / self.initial_capital) - 1) * 100
        self.equity_curve.append({
            'date': self.end_date.strftime('%Y-%m-%d'),
            'value': final_value,
            'return_pct': total_return,
        })

        return self.generate_report()

    # ──────────────────────────────────────────────────────────────────
    # Rapor
    # ──────────────────────────────────────────────────────────────────

    def generate_report(self):
        final_value  = float(self.current_capital)
        total_return = ((final_value / self.initial_capital) - 1) * 100

        market   = getattr(self, '_market', 'US')
        currency = '₺' if market == 'BIST' else '$'

        trades  = [t for t in self.history if t['action'] == 'SELL']
        winners = [t for t in trades if t.get('profit', 0) > 0]
        losers  = [t for t in trades if t.get('profit', 0) <= 0]
        win_rate = (len(winners) / len(trades) * 100) if trades else 0
        avg_win  = float(np.mean([t['profit_pct'] for t in winners])) if winners else 0
        avg_loss = float(np.mean([t['profit_pct'] for t in losers]))  if losers  else 0

        vals = [e['value'] for e in self.equity_curve]
        peak, max_dd = vals[0], 0
        for v in vals:
            if v > peak:
                peak = v
            dd = ((v - peak) / peak) * 100
            if dd < max_dd:
                max_dd = dd

        rets = pd.Series([e['return_pct'] for e in self.equity_curve])
        sharpe = float(rets.mean() / rets.std()) if rets.std() > 0 else 0

        report = {
            'summary': {
                'start_date':       self.start_date.strftime('%Y-%m-%d'),
                'end_date':         self.end_date.strftime('%Y-%m-%d'),
                'market':           market,
                'currency':         currency,
                'currency_name':    'TL' if market == 'BIST' else 'USD',
                'initial_capital':  self.initial_capital,
                'final_value':      final_value,
                'total_return':     total_return,
                'total_return_pct': total_return,
                'max_drawdown':     max_dd,
                'sharpe_ratio':     sharpe,
                'total_trades':     len(trades),
                'winning_trades':   len(winners),
                'losing_trades':    len(losers),
                'win_rate':         win_rate,
                'avg_win_pct':      avg_win,
                'avg_loss_pct':     avg_loss,
            },
            'equity_curve':  self.equity_curve,
            'trade_history': self.history,
        }

        print("\n" + "=" * 70)
        print("📊 BACKTEST SONUÇLARI")
        print("=" * 70)
        print(f"💰 Başlangıç : {currency}{self.initial_capital:,.2f}")
        print(f"💵 Son Değer : {currency}{final_value:,.2f}")
        print(f"📈 Toplam    : {total_return:+.2f}%")
        print(f"📉 Max DD    : {max_dd:.2f}%")
        print(f"📊 Sharpe    : {sharpe:.2f}")
        print(f"🎯 Win Rate  : {win_rate:.1f}%  ({len(winners)}K / {len(losers)}K)")
        print(f"🔄 İşlemler  : {len(trades)}")
        print("=" * 70)

        return report


if __name__ == "__main__":
    bt = MinerviniBacktest("2023-01-01", "2024-12-31", 100000)
    report = bt.run_backtest(market='BIST')
    with open('backtest_report.json', 'w') as f:
        json.dump(report, f, indent=2)
    print("✅ Rapor kaydedildi: backtest_report.json")

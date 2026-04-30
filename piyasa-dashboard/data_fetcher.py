import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from config import BIST_TICKERS, SP500_TICKERS, BIST_SECTOR_MAP


def _get_evds():
    key = os.environ.get("TCMB_EVDS_API_KEY", "")
    if not key:
        return None
    try:
        from evds import evdsAPI
        return evdsAPI(key)
    except ImportError:
        return None


@st.cache_data(ttl=3600)
def fetch_tcmb_policy_rate():
    try:
        evds = _get_evds()
        if evds is None:
            return None
        from datetime import datetime, timedelta
        now = datetime.now()
        start = (now - timedelta(days=90)).strftime("%d-%m-%Y")
        end = now.strftime("%d-%m-%Y")
        df = evds.get_data(["TP.APIFON4"], startdate=start, enddate=end)
        if df is not None and not df.empty:
            val = df["TP_APIFON4"].dropna().iloc[-1]
            return float(val)
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600)
def fetch_tcmb_inflation():
    try:
        evds = _get_evds()
        if evds is None:
            return None
        from datetime import datetime, timedelta
        now = datetime.now()
        start = (now - timedelta(days=540)).strftime("%d-%m-%Y")
        end = now.strftime("%d-%m-%Y")
        df = evds.get_data(["TP.FG.J0"], startdate=start, enddate=end)
        if df is not None and len(df) >= 13:
            latest = df["TP_FG_J0"].dropna().iloc[-1]
            year_ago = df["TP_FG_J0"].dropna().iloc[-13]
            yoy = (latest / year_ago - 1) * 100
            return round(yoy, 2)
    except Exception:
        pass
    return None


@st.cache_data(ttl=600)
def fetch_turkey_cds():
    from bs4 import BeautifulSoup
    import re

    urls = [
        "https://tr.investing.com/rates-bonds/turkey-cds-5-year-usd",
        "https://www.investing.com/rates-bonds/turkey-cds-5-year-usd",
    ]

    for url in urls:
        try:
            from curl_cffi import requests as curl_requests
            response = curl_requests.get(url, impersonate="chrome", timeout=15, headers={
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
                "Referer": "https://www.google.com/",
            })
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                el = soup.find(attrs={"data-test": "instrument-price-last"})
                cds_val = None
                cds_change = None
                cds_change_pct = None
                if el:
                    val_text = el.text.strip().replace(",", ".").replace("\xa0", "").replace(" ", "")
                    cds_val = float(val_text)
                change_el = soup.find(attrs={"data-test": "instrument-price-change"})
                if change_el:
                    try:
                        cds_change = float(change_el.text.strip().replace(",", ".").replace("+", "").replace("\xa0", ""))
                    except Exception:
                        pass
                change_pct_el = soup.find(attrs={"data-test": "instrument-price-change-percent"})
                if change_pct_el:
                    try:
                        pct_text = change_pct_el.text.strip().replace(",", ".").replace("(", "").replace(")", "").replace("%", "").replace("+", "").replace("\xa0", "")
                        cds_change_pct = float(pct_text)
                    except Exception:
                        pass
                if cds_val is not None:
                    return cds_val, cds_change, cds_change_pct
                for pattern in [r'"last":\s*([\d.]+)', r'"instrument_last":\s*"?([\d.,]+)"?']:
                    match = re.search(pattern, response.text)
                    if match:
                        val = match.group(1).replace(",", ".")
                        return float(val), cds_change, cds_change_pct
        except Exception:
            pass

    for url in urls:
        try:
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8",
                "Referer": "https://www.google.com/",
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            el = soup.find(attrs={"data-test": "instrument-price-last"})
            if el:
                val_text = el.text.strip().replace(",", ".").replace("\xa0", "").replace(" ", "")
                return float(val_text), None, None
        except Exception:
            pass
    return None, None, None


@st.cache_data(ttl=600)
def fetch_spy_put_call_ratio():
    """
    CBOE Total Put/Call Ratio otomatik çekilemiyor (JS render).
    Doğru değer için: https://www.cboe.com/us/options/market_statistics/daily/
    → "TOTAL PUT/CALL RATIO" satırını okuyun.
    """
    return None, None, None, None
def fetch_spy_put_call_ratio():
    """
    CBOE üzerinden SPY options volume bazlı Put/Call oranı hesaplar.
    Trading günlerinde otomatik çalışır; hafta sonu/tatil günlerinde
    None döner (son değer session state'te tutulur).
    Gerçek CBOE Total PCR için: https://www.cboe.com/us/options/market_statistics/daily/
    """
    import re, requests as _req
    try:
        r = _req.get(
            "https://cdn.cboe.com/api/global/delayed_quotes/options/SPY.json",
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        options = r.json()["data"]["options"]
        put_vol = sum(o.get("volume") or 0 for o in options if re.search(r"\d+P\d+", o.get("option", "")))
        call_vol = sum(o.get("volume") or 0 for o in options if re.search(r"\d+C\d+", o.get("option", "")))
        if call_vol > 10000:  # Trading günü — yeterli veri var
            pcr = round(put_vol / call_vol, 2)
            return pcr, None, "SPY Options (CBOE, otomatik)", None
        # Hafta sonu veya tatil — veri yok
        return None, None, "Piyasa kapalı", None
    except Exception as e:
        return None, None, f"Bağlantı hatası: {e}", None


@st.cache_data(ttl=600)
def fetch_index_history(symbol, period="1y"):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if hist.empty:
            return None
        return hist
    except Exception:
        return None


@st.cache_data(ttl=600)
def fetch_vix_data():
    try:
        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1y")
        if hist.empty:
            return None, None, None
        hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
        current = hist["Close"].iloc[-1]
        prev_5d = hist["Close"].iloc[-6] if len(hist) >= 6 else None
        change_5d = current - prev_5d if prev_5d else None
        return current, change_5d, hist
    except Exception:
        return None, None, None


@st.cache_data(ttl=600)
def fetch_treasury_yield():
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        if hist.empty:
            return None
        return hist["Close"].iloc[-1]
    except Exception:
        return None


@st.cache_data(ttl=600)
def fetch_dxy_data():
    try:
        dxy = yf.Ticker("DX-Y.NYB")
        hist = dxy.history(period="2y")
        if hist.empty:
            return None, None, None, None
        hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
        current = hist["Close"].iloc[-1]
        sma50 = hist["Close"].rolling(50).mean().dropna()
        sma200 = hist["Close"].rolling(200).mean().dropna()
        sma50_val = sma50.iloc[-1] if len(sma50) > 0 else None
        sma200_val = sma200.iloc[-1] if len(sma200) > 0 else None
        return current, sma50_val, sma200_val, hist
    except Exception:
        return None, None, None, None


@st.cache_data(ttl=600)
def fetch_usdtry_data(period="1y"):
    try:
        ticker = yf.Ticker("USDTRY=X")
        hist = ticker.history(period=period)
        if hist.empty:
            return None
        hist.index = hist.index.tz_localize(None) if hist.index.tz else hist.index
        return hist
    except Exception:
        return None


@st.cache_data(ttl=600)
def fetch_multi_ticker_data(tickers, period="3mo"):
    try:
        data = yf.download(tickers, period=period, progress=False, threads=True)
        result = {}
        if isinstance(data.columns, pd.MultiIndex):
            for ticker in tickers:
                try:
                    close = data["Close"][ticker].dropna()
                    if len(close) > 0:
                        result[ticker] = close
                except Exception:
                    continue
        else:
            if "Close" in data.columns and len(tickers) == 1:
                result[tickers[0]] = data["Close"].dropna()
        return result
    except Exception:
        return {}


@st.cache_data(ttl=600)
def fetch_sector_data(sector_map, period="3mo"):
    all_tickers = []
    for tickers in sector_map.values():
        all_tickers.extend(tickers)
    all_tickers = list(set(all_tickers))
    all_data = fetch_multi_ticker_data(all_tickers, period=period)
    result = {}
    for sector_name, tickers in sector_map.items():
        sector_data = {}
        for t in tickers:
            if t in all_data:
                sector_data[t] = all_data[t]
        result[sector_name] = sector_data
    return result


@st.cache_data(ttl=600)
def fetch_relative_strength_data():
    try:
        spy = yf.Ticker("SPY")
        qqq = yf.Ticker("QQQ")
        iwm = yf.Ticker("IWM")
        rsp = yf.Ticker("RSP")
        spy_hist = spy.history(period="6mo")
        qqq_hist = qqq.history(period="6mo")
        iwm_hist = iwm.history(period="6mo")
        rsp_hist = rsp.history(period="6mo")
        return {
            "SPY": spy_hist["Close"] if not spy_hist.empty else None,
            "QQQ": qqq_hist["Close"] if not qqq_hist.empty else None,
            "IWM": iwm_hist["Close"] if not iwm_hist.empty else None,
            "RSP": rsp_hist["Close"] if not rsp_hist.empty else None,
        }
    except Exception:
        return {}


@st.cache_data(ttl=600)
def fetch_usa_data_via_twelvedata(symbol, api_key):
    if not api_key:
        return None
    try:
        import requests
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1day&outputsize=300&apikey={api_key}"
        r = requests.get(url, timeout=15)
        data = r.json()
        if "values" not in data:
            return None
        df = pd.DataFrame(data["values"])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.set_index("datetime").sort_index()
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.columns = [c.capitalize() for c in df.columns]
        return df
    except Exception:
        return None


def generate_mock_data(market="BIST"):
    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=300, freq="B")
    base = 10000 if market == "BIST" else 5000
    returns = np.random.normal(0.0003, 0.015, len(dates))
    close = base * np.exp(np.cumsum(returns))
    volume = np.random.randint(500_000_000, 2_000_000_000, len(dates))
    high = close * (1 + np.abs(np.random.normal(0, 0.005, len(dates))))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, len(dates))))
    df = pd.DataFrame({
        "Open": close * (1 + np.random.normal(0, 0.002, len(dates))),
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)
    return df

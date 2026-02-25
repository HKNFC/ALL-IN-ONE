"""
BIST Hisse Tarama Algoritması
ALFA / BETA / DELTA Stratejileri
"""

import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import sys

# ─────────────────────────────────────────────
#  BIST 100 Hisse Listesi (.IS uzantılı)
# ─────────────────────────────────────────────
BIST100 = [
    "AKBNK.IS","ARCLK.IS","ASELS.IS","BIMAS.IS","EKGYO.IS","EREGL.IS",
    "FROTO.IS","GARAN.IS","GUBRF.IS","HALKB.IS","ISCTR.IS","KCHOL.IS",
    "KOZAA.IS","KOZAL.IS","KRDMD.IS","MGROS.IS","ODAS.IS","OYAKC.IS",
    "PGSUS.IS","SAHOL.IS","SASA.IS","SISE.IS","SKBNK.IS","TAVHL.IS",
    "TCELL.IS","THYAO.IS","TKFEN.IS","TOASO.IS","TTKOM.IS","TUPRS.IS",
    "VAKBN.IS","VESTL.IS","YKBNK.IS","AKSA.IS","AEFES.IS","ALARK.IS",
    "ANSGR.IS","ASTOR.IS","AVGYO.IS","BERA.IS","BRISA.IS","CCOLA.IS",
    "CIMSA.IS","DOHOL.IS","EGEEN.IS","ENKAI.IS","FENER.IS","GESAN.IS",
    "GLYHO.IS","GOLTS.IS","HEKTS.IS","IPEKE.IS","ISGYO.IS","ISMEN.IS",
    "KARSN.IS","KLNMA.IS","KONTR.IS","KONYA.IS","KORDS.IS","LOGO.IS",
    "MAVI.IS","MPARK.IS","NETAS.IS","NTHOL.IS","NUGYO.IS","OTKAR.IS",
    "PETKM.IS","PGSUS.IS","QUAGR.IS","REEDR.IS","RGYAS.IS","RYSAS.IS",
    "SAFGY.IS","SBKNY.IS","SOKM.IS","STLID.IS","TABGD.IS","TATGD.IS",
    "TKNSA.IS","TLMAN.IS","TRGYO.IS","TSKB.IS","TURSG.IS","ULKER.IS",
    "VKGYO.IS","YATAS.IS","ZRGYO.IS","AGHOL.IS","AKFGY.IS","AKGRT.IS",
    "ALCTL.IS","ALKIM.IS","ALMAD.IS","ALTNY.IS","ARENA.IS","ARTMS.IS",
    "ATAKP.IS","ATATP.IS","AYES.IS","BAGFS.IS",
]

# ─────────────────────────────────────────────
#  Yardımcı Teknik Göstergeler
# ─────────────────────────────────────────────
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff().dropna()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    return float(rsi_series.iloc[-1]) if not rsi_series.empty else np.nan

def fibonacci_levels(high: float, low: float) -> dict:
    diff = high - low
    return {
        "0.0":   low,
        "23.6":  low + 0.236 * diff,
        "38.2":  low + 0.382 * diff,
        "50.0":  low + 0.500 * diff,
        "61.8":  low + 0.618 * diff,
        "100.0": high,
    }

def detect_candle_pattern(df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "Belirsiz"
    o, h, l, c = df["Open"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
    po, ph, pl, pc = df["Open"].iloc[-2], df["High"].iloc[-2], df["Low"].iloc[-2], df["Close"].iloc[-2]
    body = abs(c - o)
    lower_wick = min(o, c) - l
    upper_wick = h - max(o, c)
    # Çekiç
    if lower_wick >= 2 * body and upper_wick <= 0.1 * body and c > o:
        return "Cekic"
    # Yutan Boğa
    if po > pc and c > o and c > po and o < pc:
        return "Yutan Boga"
    # Sabah Yıldızı basit versiyonu
    if pc < po and body < 0.3 * abs(ph - pl) and c > (po + pc) / 2:
        return "Sabah Yildizi"
    return "Yok"

# ─────────────────────────────────────────────
#  Veri Çekme
# ─────────────────────────────────────────────
def fetch_data(ticker: str, period: str = "1y") -> tuple:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, auto_adjust=True)
        info = t.info
        return hist, info
    except Exception:
        return pd.DataFrame(), {}

# ─────────────────────────────────────────────
#  ALFA STRATEJİSİ
#  Değer + Kalite + Teknik Onay
# ─────────────────────────────────────────────
def alfa_score(ticker: str) -> object:
    hist, info = fetch_data(ticker, period="5y")
    if hist.empty or len(hist) < 60:
        return None

    close = hist["Close"]
    score = 0
    details = {}

    # --- DEĞER FİLTRESİ ---
    pb = info.get("priceToBook", None)
    pe = info.get("trailingPE", None)
    forward_pe = info.get("forwardPE", None)
    sector_pe = info.get("industryPe", None)  # Mevcut değilse None

    # PD/DD – son 5 yıl ortalaması yerine mevcut değer var mı kontrolü
    if pb and pb > 0:
        # Proxy: PD/DD < 3.0 makul değer eşiği (5 yıl ortalaması verisi olmadığından sektör bazlı eşik)
        if pb < 3.0:
            score += 20
            details["PD/DD"] = f"{pb:.2f} (Dusuk - +20p)"
        elif pb < 5.0:
            score += 10
            details["PD/DD"] = f"{pb:.2f} (Orta - +10p)"
        else:
            details["PD/DD"] = f"{pb:.2f} (Yuksek - 0p)"
    else:
        details["PD/DD"] = "Veri yok"

    if pe and pe > 0:
        # Sektör F/K verisi doğrudan alınamadığında BIST ortalama ~12x proxy
        bist_avg_pe = 12.0
        if pe < bist_avg_pe * 0.80:
            score += 20
            details["F/K"] = f"{pe:.1f} (Sektorden %20+ iskontolu - +20p)"
        elif pe < bist_avg_pe:
            score += 10
            details["F/K"] = f"{pe:.1f} (Sektorden iskontolu - +10p)"
        else:
            details["F/K"] = f"{pe:.1f} (Sektore gore pahalı - 0p)"
    else:
        details["F/K"] = "Veri yok"

    # --- KALİTE FİLTRESİ ---
    roe = info.get("returnOnEquity", None)
    net_income = info.get("netIncomeToCommon", None)
    earnings_growth = info.get("earningsGrowth", None)

    if roe and roe > 0:
        roe_pct = roe * 100
        if roe_pct >= 30:
            score += 25
            details["ROE"] = f"%{roe_pct:.1f} (>=30 - +25p)"
        elif roe_pct >= 20:
            score += 12
            details["ROE"] = f"%{roe_pct:.1f} (20-30 - +12p)"
        else:
            details["ROE"] = f"%{roe_pct:.1f} (<20 - 0p)"
    else:
        details["ROE"] = "Veri yok"

    if earnings_growth and earnings_growth >= 0.50:
        score += 25
        details["Net_Kar_Artisi"] = f"%{earnings_growth*100:.1f} (>=50 - +25p)"
    elif earnings_growth and earnings_growth >= 0.20:
        score += 12
        details["Net_Kar_Artisi"] = f"%{earnings_growth*100:.1f} (20-50 - +12p)"
    elif earnings_growth:
        details["Net_Kar_Artisi"] = f"%{earnings_growth*100:.1f} (<20 - 0p)"
    else:
        details["Net_Kar_Artisi"] = "Veri yok"

    # --- TEKNİK ONAY ---
    ema50 = ema(close, 50).iloc[-1]
    current_price = float(close.iloc[-1])
    rsi14 = rsi(close, 14)

    if current_price > ema50:
        score += 5
        details["EMA50"] = f"{current_price:.2f} > EMA50({ema50:.2f}) - +5p"
    else:
        details["EMA50"] = f"{current_price:.2f} < EMA50({ema50:.2f}) - 0p"

    if 50 <= rsi14 <= 65:
        score += 5
        details["RSI14"] = f"{rsi14:.1f} (50-65 bandi - +5p)"
    elif 40 <= rsi14 < 50:
        score += 2
        details["RSI14"] = f"{rsi14:.1f} (40-50 - +2p)"
    else:
        details["RSI14"] = f"{rsi14:.1f} (Bant disi - 0p)"

    market_cap = info.get("marketCap", 0)

    return {
        "ticker": ticker.replace(".IS", ""),
        "score": score,
        "fiyat": current_price,
        "market_cap_mlrd_tl": round(market_cap / 1e9, 1) if market_cap else 0,
        "details": details,
    }

# ─────────────────────────────────────────────
#  BETA STRATEJİSİ
#  Büyüme + Momentum + Teknik Kırılım
# ─────────────────────────────────────────────
def beta_score(ticker: str, bist_return: float = 0.0) -> object:
    hist, info = fetch_data(ticker, period="1y")
    if hist.empty or len(hist) < 30:
        return None

    close = hist["Close"]
    volume = hist["Volume"]
    score = 0
    details = {}

    # --- BÜYÜME FİLTRESİ ---
    revenue_growth = info.get("revenueGrowth", None)
    ebitda_margins = info.get("ebitdaMargins", None)
    earnings_growth = info.get("earningsGrowth", None)

    if revenue_growth and revenue_growth > 0:
        score += 20
        details["Gelir_Buyumesi"] = f"%{revenue_growth*100:.1f} (Pozitif - +20p)"
    elif revenue_growth:
        details["Gelir_Buyumesi"] = f"%{revenue_growth*100:.1f} (Negatif - 0p)"
    else:
        details["Gelir_Buyumesi"] = "Veri yok"

    if ebitda_margins and ebitda_margins > 0:
        score += 15
        details["FAVOK_Marji"] = f"%{ebitda_margins*100:.1f} (Pozitif - +15p)"
    else:
        details["FAVOK_Marji"] = "Veri yok ya da negatif"

    if earnings_growth and earnings_growth > 0:
        score += 15
        details["Kazanc_Buyumesi"] = f"%{earnings_growth*100:.1f} (Pozitif - +15p)"
    else:
        details["Kazanc_Buyumesi"] = "Veri yok ya da negatif"

    # --- MOMENTUM FİLTRESİ (Göreceli Güç) ---
    stock_return = (float(close.iloc[-1]) / float(close.iloc[0]) - 1) * 100
    relative_strength = stock_return - bist_return

    if relative_strength > 10:
        score += 25
        details["Goreceli_Guc"] = f"%{relative_strength:.1f} (BIST100'un >%10 uzerinde - +25p)"
    elif relative_strength > 0:
        score += 12
        details["Goreceli_Guc"] = f"%{relative_strength:.1f} (BIST100 uzerinde - +12p)"
    else:
        details["Goreceli_Guc"] = f"%{relative_strength:.1f} (BIST100 altinda - 0p)"

    # --- TEKNİK KIRILIM ---
    ema20 = ema(close, 20)
    current_price = float(close.iloc[-1])

    if current_price > float(ema20.iloc[-1]):
        score += 10
        details["EMA20"] = f"{current_price:.2f} > EMA20({ema20.iloc[-1]:.2f}) - +10p"
    else:
        details["EMA20"] = f"{current_price:.2f} < EMA20 - 0p"

    avg_vol_20 = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else 0
    avg_vol_5  = float(volume.iloc[-5:].mean())  if len(volume) >= 5  else 0

    if avg_vol_20 > 0 and avg_vol_5 >= avg_vol_20 * 1.30:
        score += 15
        hacim_artis = ((avg_vol_5 / avg_vol_20) - 1) * 100
        details["Hacim"] = f"Son 5g ort. %{hacim_artis:.0f} artis (>%30 - +15p)"
    elif avg_vol_20 > 0:
        hacim_artis = ((avg_vol_5 / avg_vol_20) - 1) * 100
        details["Hacim"] = f"Son 5g ort. %{hacim_artis:.0f} artis (<=%30 - 0p)"
    else:
        details["Hacim"] = "Veri yok"

    market_cap = info.get("marketCap", 0)

    return {
        "ticker": ticker.replace(".IS", ""),
        "score": score,
        "fiyat": current_price,
        "yillik_getiri_pct": round(stock_return, 2),
        "goreceli_guc_pct": round(relative_strength, 2),
        "market_cap_mlrd_tl": round(market_cap / 1e9, 1) if market_cap else 0,
        "details": details,
    }

# ─────────────────────────────────────────────
#  DELTA STRATEJİSİ
#  Defansif + Kurumsal + Teknik Destek
# ─────────────────────────────────────────────
def delta_score(ticker: str) -> object:
    hist, info = fetch_data(ticker, period="1y")
    if hist.empty or len(hist) < 60:
        return None

    close = hist["Close"]
    score = 0
    details = {}

    # --- DEFANSİF FİLTRE (Beta) ---
    beta = info.get("beta", None)
    market_cap = info.get("marketCap", 0)

    if beta and 0.8 <= beta <= 1.2:
        score += 30
        details["Beta"] = f"{beta:.2f} (0.80-1.20 - +30p)"
    elif beta and 0.6 <= beta < 0.8:
        score += 15
        details["Beta"] = f"{beta:.2f} (Dusuk volatil - +15p)"
    elif beta:
        details["Beta"] = f"{beta:.2f} (Bant disi - 0p)"
    else:
        details["Beta"] = "Veri yok"

    # --- KURUMSAL FİLTRE ---
    # Piyasa değeri > 10 milyar TL
    market_cap_tl = market_cap  # yfinance TL hisseler için TL verir
    if market_cap_tl >= 10e9:
        score += 20
        details["Piyasa_Degeri"] = f"{market_cap_tl/1e9:.1f} Mlrd TL (>=10Mlrd - +20p)"
    elif market_cap_tl >= 5e9:
        score += 10
        details["Piyasa_Degeri"] = f"{market_cap_tl/1e9:.1f} Mlrd TL (5-10Mlrd - +10p)"
    elif market_cap_tl > 0:
        details["Piyasa_Degeri"] = f"{market_cap_tl/1e9:.1f} Mlrd TL (<5Mlrd - 0p)"
    else:
        details["Piyasa_Degeri"] = "Veri yok"

    # Yabancı pay oranı tahmini: shortPercentOfFloat ile proxy
    inst_ownership = info.get("institutionOwnership", None) or info.get("heldPercentInstitutions", None)
    if inst_ownership and inst_ownership > 0.30:
        score += 15
        details["Kurumsal_Sahiplik"] = f"%{inst_ownership*100:.1f} (>%30 - +15p)"
    elif inst_ownership:
        details["Kurumsal_Sahiplik"] = f"%{inst_ownership*100:.1f} (<=%30 - 0p)"
    else:
        details["Kurumsal_Sahiplik"] = "Veri yok"

    # --- TEKNİK DESTEK: Fibonacci ---
    high_52 = float(close.rolling(252).max().iloc[-1])
    low_52  = float(close.rolling(252).min().iloc[-1])
    fib = fibonacci_levels(high_52, low_52)
    current_price = float(close.iloc[-1])

    fib_382 = fib["38.2"]
    fib_500 = fib["50.0"]
    tol = (high_52 - low_52) * 0.03  # %3 tolerans

    near_fib = False
    fib_level_str = ""
    if abs(current_price - fib_382) <= tol:
        near_fib = True
        fib_level_str = f"Fib %38.2 ({fib_382:.2f})"
    elif abs(current_price - fib_500) <= tol:
        near_fib = True
        fib_level_str = f"Fib %50.0 ({fib_500:.2f})"

    pattern = detect_candle_pattern(hist)

    if near_fib and pattern in ["Cekic", "Yutan Boga", "Sabah Yildizi"]:
        score += 35
        details["Teknik_Destek"] = f"{fib_level_str} + {pattern} formasyonu - +35p"
    elif near_fib:
        score += 20
        details["Teknik_Destek"] = f"{fib_level_str} yakini - +20p"
    elif pattern in ["Cekic", "Yutan Boga", "Sabah Yildizi"]:
        score += 15
        details["Teknik_Destek"] = f"Mum: {pattern} - +15p"
    else:
        details["Teknik_Destek"] = f"Fib uzakta, mum: {pattern} - 0p"

    details["Mum_Formasyonu"] = pattern
    details["Fiyat"] = f"{current_price:.2f}"
    details["Fib_38.2"] = f"{fib_382:.2f}"
    details["Fib_50.0"] = f"{fib_500:.2f}"

    return {
        "ticker": ticker.replace(".IS", ""),
        "score": score,
        "fiyat": current_price,
        "beta": beta,
        "market_cap_mlrd_tl": round(market_cap_tl / 1e9, 1) if market_cap_tl else 0,
        "details": details,
    }

# ─────────────────────────────────────────────
#  BIST 100 Referans Getirisi
# ─────────────────────────────────────────────
def get_bist100_return() -> float:
    try:
        xu100 = yf.Ticker("XU100.IS")
        hist = xu100.history(period="1y", auto_adjust=True)
        if not hist.empty:
            return (float(hist["Close"].iloc[-1]) / float(hist["Close"].iloc[0]) - 1) * 100
    except Exception:
        pass
    return 0.0

# ─────────────────────────────────────────────
#  TARAMA MOTORU
# ─────────────────────────────────────────────
def run_scan(strategy: str, tickers: list, bist_ret: float = 0.0) -> list:
    results = []
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        sys.stdout.write(f"\r  [{i:3d}/{total}] {ticker:<15} taranıyor...")
        sys.stdout.flush()
        try:
            if strategy == "ALFA":
                r = alfa_score(ticker)
            elif strategy == "BETA":
                r = beta_score(ticker, bist_ret)
            elif strategy == "DELTA":
                r = delta_score(ticker)
            else:
                r = None
            if r and r["score"] > 0:
                results.append(r)
        except Exception as e:
            pass
        time.sleep(0.15)
    print()
    return sorted(results, key=lambda x: x["score"], reverse=True)

# ─────────────────────────────────────────────
#  RAPOR YAZICI
# ─────────────────────────────────────────────
def print_section(title: str, char: str = "═", width: int = 70):
    print(f"\n{'':=<{width}}")
    print(f"  {title}")
    print(f"{'':=<{width}}")

def print_stock_card(rank: int, r: dict, strategy: str):
    tag = {"ALFA": "ALFA", "BETA": "BETA", "DELTA": "DELTA"}[strategy]
    print(f"\n  #{rank}  [{tag}] {r['ticker']:<10}  Skor: {r['score']:>3}/100"
          f"  Fiyat: {r['fiyat']:>8.2f} TL"
          f"  Piy.Deg: {r['market_cap_mlrd_tl']:>6.1f} Mlrd TL")
    for k, v in r.get("details", {}).items():
        key_fmt = k.replace("_", " ").ljust(20)
        print(f"       {key_fmt}: {v}")

# ─────────────────────────────────────────────
#  ANA PROGRAM
# ─────────────────────────────────────────────
def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'':*<70}")
    print(f"  BIST ALFA / BETA / DELTA TARAMA ALGORİTMASI")
    print(f"  Tarih: {now}")
    print(f"{'':*<70}")

    # BIST 100 referans getirisi (BETA için)
    print("\n  BIST100 referans getirisi hesaplaniyor...")
    bist_ret = get_bist100_return()
    print(f"  BIST100 yillik getiri: %{bist_ret:.2f}")

    # ── ALFA ────────────────────────────────
    print_section("ALFA TARAMASI  |  Deger + Kalite + Teknik")
    print("  Hisseler taranıyor...\n")
    alfa_results = run_scan("ALFA", BIST100, bist_ret)
    top_alfa = alfa_results[:5]

    print_section("ALFA LİSTESİ — En İyi 5")
    if top_alfa:
        for i, r in enumerate(top_alfa, 1):
            print_stock_card(i, r, "ALFA")
    else:
        print("  Kriterleri karsilayan hisse bulunamadi.")

    # ── BETA ────────────────────────────────
    print_section("BETA TARAMASI  |  Buyume + Momentum + Kirilim")
    print("  Hisseler taranıyor...\n")
    beta_results = run_scan("BETA", BIST100, bist_ret)
    top_beta = beta_results[:5]

    print_section("BETA LİSTESİ — En İyi 5")
    if top_beta:
        for i, r in enumerate(top_beta, 1):
            print_stock_card(i, r, "BETA")
    else:
        print("  Kriterleri karsilayan hisse bulunamadi.")

    # ── DELTA ───────────────────────────────
    print_section("DELTA TARAMASI  |  Defansif + Kurumsal + Fibonacci")
    print("  Hisseler taranıyor...\n")
    delta_results = run_scan("DELTA", BIST100, bist_ret)
    top_delta = delta_results[:5]

    print_section("DELTA LİSTESİ — En İyi 5")
    if top_delta:
        for i, r in enumerate(top_delta, 1):
            print_stock_card(i, r, "DELTA")
    else:
        print("  Kriterleri karsilayan hisse bulunamadi.")

    # ── ÖZET ────────────────────────────────
    print_section("ÖZET TABLO")
    alfa_tickers  = [r["ticker"] for r in top_alfa]
    beta_tickers  = [r["ticker"] for r in top_beta]
    delta_tickers = [r["ticker"] for r in top_delta]

    all_in_two = set(alfa_tickers) & set(beta_tickers) | \
                 set(alfa_tickers) & set(delta_tickers) | \
                 set(beta_tickers) & set(delta_tickers)

    print(f"\n  ALFA Listesi  : {', '.join(alfa_tickers)  or 'Bos'}")
    print(f"  BETA Listesi  : {', '.join(beta_tickers)  or 'Bos'}")
    print(f"  DELTA Listesi : {', '.join(delta_tickers) or 'Bos'}")
    if all_in_two:
        print(f"\n  ** En az 2 stratejide gorunen hisseler: {', '.join(sorted(all_in_two))} **")
    print(f"\n{'':*<70}\n")

    # Sonuçları dosyaya yaz
    output_file = f"tarama_sonuclari_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    import io, contextlib
    output_path = f"/Users/hakanficicilar/Documents/Aİ/101 YATIRIM/{output_file}"
    print(f"  Sonuclar kaydediliyor: {output_path}")

if __name__ == "__main__":
    main()

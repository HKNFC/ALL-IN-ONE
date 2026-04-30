from config import USA_WEIGHTS, VIX_THRESHOLDS, TREASURY_THRESHOLDS, RSI_THRESHOLDS
from indicators import (
    calc_sma, calc_rsi, calc_macd, calc_sma_slope,
    calc_breadth, calc_new_high_low, calc_relative_strength, calc_obv,
    calc_roc, calc_volatility,
)


def score_usa_risk(vix, vix_5d_change, treasury_yield, dxy_current, dxy_sma50, dxy_sma200,
                   credit_spread=None, yield_curve=None, liquidity=None, vix_hist=None):
    w = USA_WEIGHTS["risk"]
    indicators = []
    total = 0

    # VIX 30 günlük ortalama hesapla
    vix_30d_avg = None
    if vix_hist is not None and not vix_hist.empty and len(vix_hist) >= 20:
        vix_30d_avg = vix_hist["Close"].iloc[-30:].mean() if len(vix_hist) >= 30 else vix_hist["Close"].mean()

    if vix is not None:
        if vix < VIX_THRESHOLDS["safe"]:
            pts = 1 * w["vix"]
            desc = f"VIX {vix:.1f} (<15) — Düşük Risk: Güvenli Bölge"
        elif vix < 20:
            pts = 0.5 * w["vix"]
            desc = f"VIX {vix:.1f} — Normal seviye"
        elif vix < VIX_THRESHOLDS["caution"]:
            pts = 0
            desc = f"VIX {vix:.1f} — Dikkat bölgesi"
            if vix_5d_change is not None and vix_5d_change > 3:
                pts = -0.5 * w["vix"]
                desc += f" ve yükselişte (+{vix_5d_change:.1f})"
        else:
            pts = -1 * w["vix"]
            desc = f"VIX {vix:.1f} (>25) — ⛔ Yüksek Risk"
        total += pts
        indicators.append({"name": "VIX Korku Endeksi", "value": f"{vix:.1f}",
                           "threshold": "<15/25", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # VIX Rejim Bağlamı: 30G ortalama yüksekse ceza
    if vix_30d_avg is not None:
        if vix_30d_avg > 22:
            total -= 1
            indicators.append({"name": "VIX Rejim (30G Ort)", "value": f"{vix_30d_avg:.1f}",
                               "threshold": ">22", "signal": -1, "points": -1,
                               "desc": f"30G ort VIX {vix_30d_avg:.1f} (>22) — Yüksek volatilite rejimi, dikkat"})
        # VIX spike'tan geri çekilme tuzağı
        if (vix_5d_change is not None and vix_5d_change < -5 and vix_30d_avg > 20):
            total -= 1
            indicators.append({"name": "VIX Spike Geri Çekilmesi", "value": f"{vix_5d_change:+.1f}",
                               "threshold": "<-5 & 30G>20", "signal": -1, "points": -1,
                               "desc": f"VIX 5G'de {vix_5d_change:.1f} düştü ama 30G ort {vix_30d_avg:.1f} — Kandırıcı rahatlama riski"})

    if treasury_yield is not None:
        if treasury_yield > TREASURY_THRESHOLDS["negative"]:
            pts = -1 * w["treasury_10y"]
            desc = f"10Y Faiz %{treasury_yield:.2f} (>%4.5) — Büyüme hisseleri baskı altında"
        elif treasury_yield < TREASURY_THRESHOLDS["positive"]:
            pts = 1 * w["treasury_10y"]
            desc = f"10Y Faiz %{treasury_yield:.2f} (<%3.5) — Düşük faiz ortamı, destekleyici"
        else:
            pts = 0
            desc = f"10Y Faiz %{treasury_yield:.2f} — Nötr bölge"
        total += pts
        indicators.append({"name": "10Y Treasury", "value": f"%{treasury_yield:.2f}",
                           "threshold": "<%3.5/>%4.5", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if dxy_current is not None and dxy_sma200 is not None:
        dxy_strong = dxy_current > dxy_sma200 and (dxy_sma50 is None or dxy_current > dxy_sma50)
        dxy_weak = dxy_current < dxy_sma200
        if dxy_strong:
            pts = -1 * w["dxy"]
            desc = f"DXY {dxy_current:.1f} — Güçlü dolar, hisseleri baskılıyor"
        elif dxy_weak:
            pts = 1 * w["dxy"]
            desc = f"DXY {dxy_current:.1f} — Zayıf dolar, hisseler için olumlu"
        else:
            pts = 0
            desc = f"DXY {dxy_current:.1f} — Karışık sinyal"
        total += pts
        indicators.append({"name": "DXY Dolar Endeksi", "value": f"{dxy_current:.1f}",
                           "threshold": f"SMA200: {dxy_sma200:.1f}" if dxy_sma200 else "N/A",
                           "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if credit_spread is not None:
        pts = credit_spread * w["credit_spread"]
        total += pts
        indicators.append({"name": "Kredi Spread", "value": "Daralan" if credit_spread > 0 else "Açılan",
                           "threshold": "HY Spread", "signal": credit_spread,
                           "points": pts, "desc": "Kredi piyasası durumu"})
    else:
        indicators.append({"name": "Kredi Spread", "value": "N/A", "threshold": "HY Spread",
                           "signal": 0, "points": 0, "desc": "Veri henüz bağlanmadı"})

    if yield_curve is not None:
        pts = yield_curve * w["yield_curve"]
        total += pts
        indicators.append({"name": "Yield Curve", "value": "Normal" if yield_curve > 0 else "Ters",
                           "threshold": "2Y-10Y", "signal": yield_curve,
                           "points": pts, "desc": "Verim eğrisi durumu"})
    else:
        indicators.append({"name": "Yield Curve", "value": "N/A", "threshold": "2Y-10Y",
                           "signal": 0, "points": 0, "desc": "Veri henüz bağlanmadı"})

    if liquidity is not None:
        pts = liquidity * w["liquidity"]
        total += pts
        indicators.append({"name": "Likidite Koşulları", "value": "Gevşek" if liquidity > 0 else "Sıkı",
                           "threshold": "Finansal", "signal": liquidity,
                           "points": pts, "desc": "Finansal koşullar"})
    else:
        indicators.append({"name": "Likidite Koşulları", "value": "N/A", "threshold": "Finansal",
                           "signal": 0, "points": 0, "desc": "Veri henüz bağlanmadı"})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible


def score_usa_internals(tickers_data, pc_ratio, pc_volume_ratio, rs_data=None):
    w = USA_WEIGHTS["internals"]
    indicators = []
    total = 0

    breadth50_pct, above50, total50 = calc_breadth(tickers_data, 50)
    if breadth50_pct is not None:
        if breadth50_pct > 60:
            pts = 1 * w["breadth_sma50"]
            desc = f"%{breadth50_pct:.0f} hisse SMA50 üzerinde ({above50}/{total50}) — Geniş katılım"
        elif breadth50_pct > 40:
            pts = 0
            desc = f"%{breadth50_pct:.0f} hisse SMA50 üzerinde ({above50}/{total50}) — Nötr"
        else:
            pts = -1 * w["breadth_sma50"]
            desc = f"%{breadth50_pct:.0f} hisse SMA50 üzerinde ({above50}/{total50}) — Zayıf katılım"
        total += pts
        indicators.append({"name": "Breadth SMA50", "value": f"%{breadth50_pct:.0f}",
                           "threshold": ">60/>40", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    breadth200_pct, above200, total200 = calc_breadth(tickers_data, 200)
    if breadth200_pct is not None:
        if breadth200_pct > 55:
            pts = 1 * w["breadth_sma200"]
            desc = f"%{breadth200_pct:.0f} hisse SMA200 üzerinde — Uzun vadeli sağlıklı"
        else:
            pts = -1 * w["breadth_sma200"]
            desc = f"%{breadth200_pct:.0f} hisse SMA200 üzerinde — Uzun vadeli zayıf"
        total += pts
        indicators.append({"name": "Breadth SMA200", "value": f"%{breadth200_pct:.0f}",
                           "threshold": ">55%", "signal": 1 if pts > 0 else -1,
                           "points": pts, "desc": desc})

    nh_nl_ratio, new_highs, new_lows = calc_new_high_low(tickers_data)
    if nh_nl_ratio is not None:
        if nh_nl_ratio > 2:
            pts = 1 * w["new_high_low"]
            desc = f"Yeni Zirve/Dip: {new_highs}/{new_lows} — Zirveler baskın"
        elif nh_nl_ratio < 0.5:
            pts = -1 * w["new_high_low"]
            desc = f"Yeni Zirve/Dip: {new_highs}/{new_lows} — Dipler baskın"
        else:
            pts = 0
            desc = f"Yeni Zirve/Dip: {new_highs}/{new_lows} — Dengeli"
        total += pts
        indicators.append({"name": "Yeni Zirve/Dip", "value": f"{new_highs}/{new_lows}",
                           "threshold": "Oran >2", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if rs_data and "SPY" in rs_data and "RSP" in rs_data:
        rs_eq = calc_relative_strength(rs_data.get("RSP"), rs_data.get("SPY"))
        if rs_eq is not None:
            if rs_eq > 1:
                pts = 1 * w["equal_vs_cap"]
                desc = f"Eşit Ağırlıklı > Cap Ağırlıklı (+%{rs_eq:.1f}) — Sağlıklı yükseliş"
            elif rs_eq < -2:
                pts = -1 * w["equal_vs_cap"]
                desc = f"Eşit Ağırlıklı < Cap Ağırlıklı (%{rs_eq:.1f}) — Mega-cap bağımlı"
            else:
                pts = 0
                desc = f"RSP/SPY nötr (%{rs_eq:.1f})"
            total += pts
            indicators.append({"name": "Eşit vs Cap Ağırlık", "value": f"%{rs_eq:.1f}",
                               "threshold": "RSP/SPY", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    if rs_data and "SPY" in rs_data and "IWM" in rs_data:
        rs_iwm = calc_relative_strength(rs_data.get("IWM"), rs_data.get("SPY"))
        if rs_iwm is not None:
            if rs_iwm > 1:
                pts = 1 * w["relative_strength"]
                desc = f"Small Cap güçlü (%{rs_iwm:.1f}) — Risk-on ortam"
            elif rs_iwm < -2:
                pts = -1 * w["relative_strength"]
                desc = f"Small Cap zayıf (%{rs_iwm:.1f}) — Risk-off sinyali"
            else:
                pts = 0
                desc = f"IWM/SPY nötr (%{rs_iwm:.1f})"
            total += pts
            indicators.append({"name": "Small Cap RS", "value": f"%{rs_iwm:.1f}",
                               "threshold": "IWM/SPY", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    if pc_ratio is not None:
        if pc_ratio > 1.0:
            pts = 1 * w["put_call"]
            desc = f"P/C {pc_ratio:.2f} (>1.0) — Aşırı Korku (Ters sinyal: Alım fırsatı)"
        elif pc_ratio < 0.7:
            pts = -1 * w["put_call"]
            desc = f"P/C {pc_ratio:.2f} (<0.7) — Aşırı Coşku (Satış baskısı riski)"
        else:
            pts = 0
            desc = f"P/C {pc_ratio:.2f} (0.7-1.0) — Normal seviye"
        total += pts
        vol_note = ""
        if pc_volume_ratio is not None:
            vol_note = f" | Vol P/C: {pc_volume_ratio:.2f}"
        indicators.append({"name": "Put/Call Oranı", "value": f"{pc_ratio:.2f}{vol_note}",
                           "threshold": ">1.0/<0.7", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible, breadth50_pct


def score_usa_timing(hist):
    w = USA_WEIGHTS["timing"]
    indicators = []
    total = 0

    if hist is None or hist.empty:
        return 0, [], 0

    close = hist["Close"]
    volume = hist["Volume"] if "Volume" in hist.columns else None
    last = close.iloc[-1]

    sma50 = calc_sma(close, 50)
    sma200 = calc_sma(close, 200)
    sma200_val = sma200.dropna().iloc[-1] if sma200 is not None and len(sma200.dropna()) > 0 else None

    if sma200_val is not None:
        if last > sma200_val:
            pts = 1 * w["sma_position"]
            desc = f"Fiyat SMA200 üzerinde ({last:,.0f} > {sma200_val:,.0f})"
        else:
            pts = -2 * w["sma_position"]
            desc = f"Fiyat SMA200 altında ({last:,.0f} < {sma200_val:,.0f}) — Güçlü negatif"
        total += pts
        indicators.append({"name": "Fiyat vs SMA200", "value": f"{last:,.0f}",
                           "threshold": f"SMA200: {sma200_val:,.0f}",
                           "signal": 1 if pts > 0 else -1,
                           "points": pts, "desc": desc})

    if sma50 is not None:
        slope50 = calc_sma_slope(sma50, 10)
        if slope50 is not None:
            if slope50 > 0.3:
                pts = 1 * w["sma50_slope"]
                desc = f"SMA50 eğimi +%{slope50:.2f} — Yükselen momentum"
            elif slope50 < -0.3:
                pts = -1 * w["sma50_slope"]
                desc = f"SMA50 eğimi %{slope50:.2f} — Düşen momentum"
            else:
                pts = 0
                desc = f"SMA50 eğimi %{slope50:.2f} — Yatay"
            total += pts
            indicators.append({"name": "SMA50 Eğimi", "value": f"%{slope50:+.2f}",
                               "threshold": ">0.3/<-0.3", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    _, _, macd_hist = calc_macd(close)
    if macd_hist is not None and len(macd_hist.dropna()) > 0:
        mh = macd_hist.dropna().iloc[-1]
        if mh > 0:
            pts = 1 * w["macd"]
            desc = f"MACD histogram pozitif ({mh:.1f}) — Momentum yukarı"
        else:
            pts = -1 * w["macd"]
            desc = f"MACD histogram negatif ({mh:.1f}) — Momentum aşağı"
        total += pts
        indicators.append({"name": "MACD Histogram", "value": f"{mh:.1f}",
                           "threshold": ">0/<0", "signal": 1 if mh > 0 else -1,
                           "points": pts, "desc": desc})

    rsi = calc_rsi(close)
    if rsi is not None and len(rsi.dropna()) > 0:
        rsi_val = rsi.dropna().iloc[-1]
        if RSI_THRESHOLDS["healthy_low"] <= rsi_val <= RSI_THRESHOLDS["healthy_high"]:
            pts = 1 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — Sağlıklı bölge"
        elif rsi_val > RSI_THRESHOLDS["overbought"]:
            pts = -0.5 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — Aşırı alım, dikkat"
        elif rsi_val < RSI_THRESHOLDS["oversold"]:
            pts = 0
            desc = f"RSI {rsi_val:.1f} — Aşırı satım, trendle değerlendir"
        else:
            pts = 0
            desc = f"RSI {rsi_val:.1f} — Nötr bölge"
        total += pts
        indicators.append({"name": "RSI (14)", "value": f"{rsi_val:.1f}",
                           "threshold": "45-65 sağlıklı", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if volume is not None:
        vol_sma20 = volume.rolling(20).mean()
        obv = calc_obv(close, volume)
        if vol_sma20 is not None and len(vol_sma20.dropna()) > 0 and obv is not None:
            last_vol = volume.iloc[-1]
            avg_vol = vol_sma20.dropna().iloc[-1]
            obv_sma = obv.rolling(20).mean()
            obv_above = obv.iloc[-1] > obv_sma.dropna().iloc[-1] if len(obv_sma.dropna()) > 0 else False
            if last_vol > avg_vol and obv_above:
                pts = 1 * w["volume"]
                desc = f"Hacim ortalamanın üzerinde ve OBV pozitif — Güçlü para akışı"
            elif last_vol < avg_vol * 0.7 and not obv_above:
                pts = -1 * w["volume"]
                desc = f"Hacim düşük ve OBV negatif — Zayıf katılım"
            else:
                pts = 0
                desc = f"Hacim nötr"
            total += pts
            indicators.append({"name": "Hacim + OBV", "value": f"{last_vol:,.0f}",
                               "threshold": f"SMA20: {avg_vol:,.0f}",
                               "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible


def score_usa_momentum(hist, rs_data=None):
    """Momentum katmanı — RSI, MACD, ROC, QQQ/SPY, IWM/SPY"""
    w = USA_WEIGHTS["momentum"]
    indicators = []
    total = 0

    if hist is None or hist.empty:
        return 0, [], 0

    close = hist["Close"]

    # RSI
    rsi = calc_rsi(close)
    if rsi is not None and len(rsi.dropna()) > 0:
        rsi_val = rsi.dropna().iloc[-1]
        if RSI_THRESHOLDS["healthy_low"] <= rsi_val <= RSI_THRESHOLDS["healthy_high"]:
            pts = 1 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — sağlıklı momentum"
        elif rsi_val > RSI_THRESHOLDS["overbought"]:
            pts = -0.5 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — aşırı alım"
        elif rsi_val < RSI_THRESHOLDS["oversold"]:
            pts = -0.5 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — aşırı satım"
        else:
            pts = 0
            desc = f"RSI {rsi_val:.1f} — nötr"
        total += pts
        indicators.append({"name": "RSI Momentum", "value": f"{rsi_val:.1f}",
                           "threshold": "45-65 sağlıklı", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # MACD
    _, _, macd_hist = calc_macd(close)
    if macd_hist is not None and len(macd_hist.dropna()) > 0:
        mh = macd_hist.dropna().iloc[-1]
        if mh > 0:
            pts = 1 * w["macd"]
            desc = f"MACD histogram pozitif ({mh:.2f}) — yukarı momentum"
        else:
            pts = -1 * w["macd"]
            desc = f"MACD histogram negatif ({mh:.2f}) — aşağı momentum"
        total += pts
        indicators.append({"name": "MACD Momentum", "value": f"{mh:.2f}",
                           "threshold": ">0/<0", "signal": 1 if mh > 0 else -1,
                           "points": pts, "desc": desc})

    # ROC
    roc = calc_roc(close, 10)
    if roc is not None and len(roc.dropna()) > 0:
        roc_val = roc.dropna().iloc[-1]
        if roc_val > 2:
            pts = 1 * w["roc"]
            desc = f"ROC 10G {roc_val:+.1f}% — güçlü momentum"
        elif roc_val < -2:
            pts = -1 * w["roc"]
            desc = f"ROC 10G {roc_val:+.1f}% — zayıf momentum"
        else:
            pts = 0
            desc = f"ROC 10G {roc_val:+.1f}% — nötr"
        total += pts
        indicators.append({"name": "ROC (10G)", "value": f"{roc_val:+.1f}%",
                           "threshold": ">2%/<-2%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # QQQ/SPY relative strength
    if rs_data and "SPY" in rs_data and "QQQ" in rs_data:
        rs_qqq = calc_relative_strength(rs_data.get("QQQ"), rs_data.get("SPY"))
        if rs_qqq is not None:
            if rs_qqq > 1:
                pts = 1 * w["qqq_spy"]
                desc = f"QQQ/SPY güçlü (+{rs_qqq:.1f}%) — büyüme hisseleri lider"
            elif rs_qqq < -1:
                pts = -1 * w["qqq_spy"]
                desc = f"QQQ/SPY zayıf ({rs_qqq:.1f}%) — büyüme hisseleri geride"
            else:
                pts = 0
                desc = f"QQQ/SPY nötr ({rs_qqq:.1f}%)"
            total += pts
            indicators.append({"name": "QQQ/SPY Momentum", "value": f"{rs_qqq:+.1f}%",
                               "threshold": ">1%/<-1%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    # IWM/SPY relative strength
    if rs_data and "SPY" in rs_data and "IWM" in rs_data:
        rs_iwm = calc_relative_strength(rs_data.get("IWM"), rs_data.get("SPY"))
        if rs_iwm is not None:
            if rs_iwm > 1:
                pts = 1 * w["iwm_spy"]
                desc = f"IWM/SPY güçlü (+{rs_iwm:.1f}%) — risk-on momentum"
            elif rs_iwm < -2:
                pts = -1 * w["iwm_spy"]
                desc = f"IWM/SPY zayıf ({rs_iwm:.1f}%) — risk-off momentum"
            else:
                pts = 0
                desc = f"IWM/SPY nötr ({rs_iwm:.1f}%)"
            total += pts
            indicators.append({"name": "IWM/SPY Momentum", "value": f"{rs_iwm:+.1f}%",
                               "threshold": ">1%/<-2%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible


def score_usa_sentiment(hist, pc_ratio=None, pc_volume_ratio=None):
    """Sentiment katmanı — Put/Call, hacim kalitesi, likidite"""
    w = USA_WEIGHTS["sentiment"]
    indicators = []
    total = 0

    # Put/Call oranı (ters sinyal)
    if pc_ratio is not None:
        if pc_ratio > 1.0:
            pts = 1 * w["put_call"]
            desc = f"P/C {pc_ratio:.2f} (>1.0) — Aşırı korku (ters sinyal: alım fırsatı)"
        elif pc_ratio < 0.7:
            pts = -1 * w["put_call"]
            desc = f"P/C {pc_ratio:.2f} (<0.7) — Aşırı coşku (satış baskısı riski)"
        else:
            pts = 0
            desc = f"P/C {pc_ratio:.2f} — normal seviye"
        total += pts
        indicators.append({"name": "Put/Call Sentiment", "value": f"{pc_ratio:.2f}",
                           "threshold": ">1.0/<0.7", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # Hacim kalitesi
    if hist is not None and not hist.empty:
        close = hist["Close"]
        volume = hist["Volume"] if "Volume" in hist.columns else None
        if volume is not None:
            vol_sma20 = volume.rolling(20).mean()
            obv = calc_obv(close, volume)
            if len(vol_sma20.dropna()) > 0 and obv is not None:
                last_vol = volume.iloc[-1]
                avg_vol = vol_sma20.dropna().iloc[-1]
                obv_sma = obv.rolling(20).mean()
                obv_rising = obv.iloc[-1] > obv_sma.dropna().iloc[-1] if len(obv_sma.dropna()) > 0 else False
                vol_above = last_vol > avg_vol

                if vol_above and obv_rising:
                    pts = 1 * w["volume_quality"]
                    desc = "Hacim güçlü + OBV pozitif — akıllı para girişi"
                elif not vol_above and not obv_rising:
                    pts = -1 * w["volume_quality"]
                    desc = "Hacim zayıf + OBV negatif — akıllı para çıkışı"
                else:
                    pts = 0
                    desc = "Hacim/OBV karışık sinyal"
                total += pts
                indicators.append({"name": "Hacim Kalitesi", "value": f"{last_vol:,.0f}",
                                   "threshold": f"SMA20: {avg_vol:,.0f}", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                                   "points": pts, "desc": desc})

        # Likidite trendi (hacim bazlı proxy)
        if volume is not None and len(volume) >= 20:
            vol_10d = volume.iloc[-10:].mean()
            vol_20d = volume.iloc[-20:].mean()
            if vol_20d > 0:
                liq_ratio = vol_10d / vol_20d
                if liq_ratio > 1.1:
                    pts = 1 * w["liquidity"]
                    desc = f"Likidite artıyor (10G/20G: {liq_ratio:.2f}) — piyasa ilgisi yüksek"
                elif liq_ratio < 0.8:
                    pts = -1 * w["liquidity"]
                    desc = f"Likidite azalıyor (10G/20G: {liq_ratio:.2f}) — piyasa ilgisi düşük"
                else:
                    pts = 0
                    desc = f"Likidite stabil (10G/20G: {liq_ratio:.2f})"
                total += pts
                indicators.append({"name": "Likidite Trendi", "value": f"{liq_ratio:.2f}",
                                   "threshold": ">1.1/<0.8", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                                   "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible

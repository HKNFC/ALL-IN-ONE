from config import BIST_WEIGHTS, CDS_THRESHOLDS, RSI_THRESHOLDS
from indicators import (
    calc_sma, calc_rsi, calc_macd, calc_adx, calc_obv,
    calc_volatility, calc_sma_slope, calc_breadth,
    calc_new_high_low, calc_sector_breadth, calc_usdtry_volatility,
    calc_roc,
)


def score_bist_macro(cds_value, real_rate, bist_usd_above_sma200, usdtry_vol_current, usdtry_vol_avg, foreign_flow=None, cds_trend=None, yabanci_oran=None, yabanci_degisim=None):
    w = BIST_WEIGHTS["macro"]
    indicators = []
    total = 0

    if cds_value is not None:
        if cds_value < CDS_THRESHOLDS["guclu_giris"]:
            pts = 1.5 * w["cds"]
            yabanci = "Güçlü Giriş"
            desc = f"CDS {cds_value:.0f} bps (<200) — Yabancı ilgisi güçlü, sermaye girişi olumlu"
        elif cds_value < CDS_THRESHOLDS["ilimli_giris"]:
            pts = 0.5 * w["cds"]
            yabanci = "Ilımlı Giriş"
            desc = f"CDS {cds_value:.0f} bps (200-300) — Yabancı ilgisi ılımlı, seçici giriş"
        elif cds_value < CDS_THRESHOLDS["zayif_ilgi"]:
            pts = -1 * w["cds"]
            yabanci = "Zayıf İlgi"
            desc = f"CDS {cds_value:.0f} bps (300-400) — Yabancı ilgisi zayıf, çıkış riski var"
        elif cds_value < CDS_THRESHOLDS["sert_cikis"]:
            pts = -1.5 * w["cds"]
            yabanci = "Sert Çıkış"
            desc = f"CDS {cds_value:.0f} bps (400-500) — Yabancı sert çıkışta, piyasa baskı altında"
        else:
            pts = -2 * w["cds"]
            yabanci = "Sistem Kapalı"
            desc = f"CDS {cds_value:.0f} bps (>500) — Kriz seviyesi, sistem kapalı"
        total += pts
        indicators.append({"name": "CDS Risk Primi", "value": f"{cds_value:.0f} bps",
                           "threshold": "<200/300/400/500", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})
        indicators.append({"name": "Yabancı İlgisi (CDS)", "value": yabanci,
                           "threshold": "CDS bazlı", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": 0, "desc": f"CDS {cds_value:.0f} bps → {yabanci}"})
    else:
        indicators.append({"name": "CDS Risk Primi", "value": "N/A", "threshold": "<200/300/400/500",
                           "signal": 0, "points": 0, "desc": "Veri alınamadı"})

    if cds_trend is not None:
        if cds_trend == "rising":
            trend_pts = -0.5 * w["cds"]
            trend_desc = "CDS yükseliyor — risk artıyor, teknik sinyallerin gücü düşürüldü"
            trend_signal = -1
        elif cds_trend == "falling":
            trend_pts = 0.5 * w["cds"]
            trend_desc = "CDS düşüyor — risk azalıyor, teknik sinyaller güçlendirildi"
            trend_signal = 1
        else:
            trend_pts = 0
            trend_desc = "CDS eğilimi yatay — nötr etki"
            trend_signal = 0
        total += trend_pts
        indicators.append({"name": "CDS Eğilimi", "value": "Yükseliyor" if cds_trend == "rising" else ("Düşüyor" if cds_trend == "falling" else "Yatay"),
                           "threshold": "5G trend", "signal": trend_signal,
                           "points": trend_pts, "desc": trend_desc})

    if real_rate is not None:
        if real_rate < -2:
            pts = 1 * w["real_rate"]
            desc = f"Reel Faiz %{real_rate:+.1f} — Güçlü negatif, borsa destekleyici"
        elif real_rate < 0:
            pts = 0.5 * w["real_rate"]
            desc = f"Reel Faiz %{real_rate:+.1f} — Hafif negatif, borsa için olumlu"
        elif real_rate < 3:
            pts = 0
            desc = f"Reel Faiz %{real_rate:+.1f} — Hafif pozitif, nötr"
        else:
            pts = -1 * w["real_rate"]
            desc = f"Reel Faiz %{real_rate:+.1f} — Yüksek pozitif, mevduat/tahvil cazip"
        total += pts
        indicators.append({"name": "Reel Faiz", "value": f"%{real_rate:+.1f}",
                           "threshold": "<0/0-3/>3", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if bist_usd_above_sma200 is not None:
        if bist_usd_above_sma200:
            pts = 1 * w["bist_usd"]
            desc = "BIST/USD SMA200 üzerinde — Dolar bazlı trend pozitif"
        else:
            pts = -1 * w["bist_usd"]
            desc = "BIST/USD SMA200 altında — Dolar bazlı trend negatif"
        total += pts
        indicators.append({"name": "BIST/USD Trend", "value": "Üzeri" if bist_usd_above_sma200 else "Altı",
                           "threshold": "SMA200", "signal": 1 if bist_usd_above_sma200 else -1,
                           "points": pts, "desc": desc})

    if usdtry_vol_current is not None and usdtry_vol_avg is not None:
        if usdtry_vol_current < usdtry_vol_avg * 0.8:
            pts = 1 * w["usdtry_vol"]
            desc = f"USDTRY Vol %{usdtry_vol_current:.1f} — Düşük oynaklık, stabil"
        elif usdtry_vol_current > usdtry_vol_avg * 1.3:
            pts = -1 * w["usdtry_vol"]
            desc = f"USDTRY Vol %{usdtry_vol_current:.1f} — Yüksek oynaklık, risk arttı"
        else:
            pts = 0
            desc = f"USDTRY Vol %{usdtry_vol_current:.1f} — Normal seviye"
        total += pts
        indicators.append({"name": "USDTRY Volatilite", "value": f"%{usdtry_vol_current:.1f}",
                           "threshold": f"Ort: %{usdtry_vol_avg:.1f}", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if yabanci_oran is not None and yabanci_degisim is not None:
        if yabanci_degisim > 1.5:
            pts = 1 * w["foreign_flow"]
            desc = f"Yabancı payı %{yabanci_oran:.1f} (↑{yabanci_degisim:+.1f}pp) — Yabancı alım eğiliminde"
            signal = 1
        elif yabanci_degisim < -1.5:
            pts = -1 * w["foreign_flow"]
            desc = f"Yabancı payı %{yabanci_oran:.1f} (↓{yabanci_degisim:+.1f}pp) — Yabancı satış eğiliminde"
            signal = -1
        else:
            pts = 0
            desc = f"Yabancı payı %{yabanci_oran:.1f} ({yabanci_degisim:+.1f}pp) — Eğilim yatay"
            signal = 0

        if yabanci_oran < 20:
            desc += ". Yabancı payı tarihsel olarak düşük — potansiyel giriş fırsatı veya yapısal çıkış"
        elif yabanci_oran > 40:
            desc += ". Yabancı payı yüksek — istikrar sinyali"

        total += pts
        indicators.append({"name": "Yabancı Takas Payı", "value": f"%{yabanci_oran:.1f}",
                           "threshold": f"Δ: {yabanci_degisim:+.1f}pp", "signal": signal,
                           "points": pts, "desc": desc})
    elif foreign_flow is not None:
        pts = foreign_flow * w["foreign_flow"]
        total += pts
        indicators.append({"name": "Yabancı İlgisi", "value": "Pozitif" if foreign_flow > 0 else "Negatif",
                           "threshold": "Akım", "signal": foreign_flow,
                           "points": pts, "desc": "Yabancı sermaye akımı"})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible


def score_bist_health(tickers_data, sector_data_map, hist=None):
    w = BIST_WEIGHTS["health"]
    indicators = []
    total = 0

    if hist is not None and not hist.empty:
        close = hist["Close"]
        volume = hist["Volume"] if "Volume" in hist.columns else None
        if volume is not None:
            obv = calc_obv(close, volume)
            vol_sma20 = volume.rolling(20).mean()
            if obv is not None and vol_sma20 is not None and len(vol_sma20.dropna()) > 0:
                last_vol = volume.iloc[-1]
                avg_vol = vol_sma20.dropna().iloc[-1]
                obv_sma = obv.rolling(20).mean()
                obv_rising = obv.iloc[-1] > obv_sma.dropna().iloc[-1] if len(obv_sma.dropna()) > 0 else False
                vol_above = last_vol > avg_vol
                if vol_above and obv_rising:
                    pts = 1 * w["volume_obv"]
                    desc = "Hacim ortalamanın üzerinde ve OBV pozitif — Güçlü para akışı"
                elif not vol_above and not obv_rising:
                    pts = -1 * w["volume_obv"]
                    desc = "Hacim düşük ve OBV negatif — Zayıf katılım"
                else:
                    pts = 0
                    desc = "Hacim/OBV karışık sinyal"
                total += pts
                indicators.append({"name": "Hacim + OBV", "value": f"{last_vol:,.0f}",
                                   "threshold": f"SMA20: {avg_vol:,.0f}",
                                   "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                                   "points": pts, "desc": desc})

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
            desc = f"%{breadth200_pct:.0f} hisse SMA200 üzerinde — Uzun vadeli trend sağlıklı"
        else:
            pts = -1 * w["breadth_sma200"]
            desc = f"%{breadth200_pct:.0f} hisse SMA200 üzerinde — Uzun vadeli trend zayıf"
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
                           "threshold": "Oran >2/<0.5", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if sector_data_map:
        sector_scores, strong_count, total_sectors = calc_sector_breadth(sector_data_map)
        if total_sectors > 0:
            if strong_count >= total_sectors * 0.6:
                pts = 1 * w["sector_leadership"]
                desc = f"{strong_count}/{total_sectors} sektör güçlü — Geniş sektör liderliği"
            elif strong_count <= 1:
                pts = -1 * w["sector_leadership"]
                desc = f"{strong_count}/{total_sectors} sektör güçlü — Dar liderlik"
            else:
                pts = 0
                desc = f"{strong_count}/{total_sectors} sektör güçlü — Kısmi liderlik"
            total += pts
            indicators.append({"name": "Sektör Liderliği", "value": f"{strong_count}/{total_sectors}",
                               "threshold": ">60%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible, breadth50_pct


def score_bist_timing(hist):
    w = BIST_WEIGHTS["timing"]
    indicators = []
    total = 0

    if hist is None or hist.empty:
        return 0, [], 0

    close = hist["Close"]
    high = hist["High"] if "High" in hist.columns else close
    low = hist["Low"] if "Low" in hist.columns else close
    volume = hist["Volume"] if "Volume" in hist.columns else None
    last = close.iloc[-1]

    sma50 = calc_sma(close, 50)
    sma200 = calc_sma(close, 200)
    sma50_val = sma50.dropna().iloc[-1] if sma50 is not None and len(sma50.dropna()) > 0 else None
    sma200_val = sma200.dropna().iloc[-1] if sma200 is not None and len(sma200.dropna()) > 0 else None

    if sma50_val is not None and sma200_val is not None:
        if last > sma50_val and last > sma200_val:
            pts = 1 * w["sma_position"]
            desc = f"Fiyat SMA50 ve SMA200 üzerinde — Güçlü trend"
        elif last < sma50_val and last < sma200_val:
            pts = -1 * w["sma_position"]
            desc = f"Fiyat SMA50 ve SMA200 altında — Zayıf trend"
        elif last > sma200_val:
            pts = 0.5 * w["sma_position"]
            desc = f"Fiyat SMA200 üzerinde ama SMA50 altında — Karışık"
        else:
            pts = -0.5 * w["sma_position"]
            desc = f"Fiyat SMA200 altında — Zayıflıyor"
        total += pts
        indicators.append({"name": "Fiyat vs SMA", "value": f"{last:,.0f}",
                           "threshold": f"SMA50:{sma50_val:,.0f} SMA200:{sma200_val:,.0f}",
                           "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    if sma50 is not None:
        slope50 = calc_sma_slope(sma50, 10)
        if slope50 is not None:
            if slope50 > 0.5:
                pts = 1 * w["sma50_slope"]
                desc = f"SMA50 eğimi +%{slope50:.2f} — Yükselen trend"
            elif slope50 < -0.5:
                pts = -1 * w["sma50_slope"]
                desc = f"SMA50 eğimi %{slope50:.2f} — Düşen trend"
            else:
                pts = 0
                desc = f"SMA50 eğimi %{slope50:.2f} — Yatay"
            total += pts
            indicators.append({"name": "SMA50 Eğimi", "value": f"%{slope50:+.2f}",
                               "threshold": ">0.5/<-0.5", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    if sma200 is not None:
        slope200 = calc_sma_slope(sma200, 10)
        if slope200 is not None:
            if slope200 > 0.3:
                pts = 1 * w["sma200_slope"]
                desc = f"SMA200 eğimi +%{slope200:.2f} — Uzun vadeli yükseliş"
            elif slope200 < -0.3:
                pts = -1 * w["sma200_slope"]
                desc = f"SMA200 eğimi %{slope200:.2f} — Uzun vadeli düşüş"
            else:
                pts = 0
                desc = f"SMA200 eğimi %{slope200:.2f} — Yatay"
            total += pts
            indicators.append({"name": "SMA200 Eğimi", "value": f"%{slope200:+.2f}",
                               "threshold": ">0.3/<-0.3", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
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
            pts = -0.5 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — Aşırı satım, trendle birlikte değerlendir"
        else:
            pts = 0
            desc = f"RSI {rsi_val:.1f} — Nötr bölge"
        total += pts
        indicators.append({"name": "RSI (14)", "value": f"{rsi_val:.1f}",
                           "threshold": "45-65 sağlıklı", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
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

    adx = calc_adx(high, low, close)
    if adx is not None and len(adx.dropna()) > 0:
        adx_val = adx.dropna().iloc[-1]
        if adx_val > 25:
            pts = 1 * w["adx"]
            desc = f"ADX {adx_val:.1f} — Güçlü trend mevcut"
        elif adx_val > 20:
            pts = 0.5 * w["adx"]
            desc = f"ADX {adx_val:.1f} — Trend gelişiyor"
        else:
            pts = -0.5 * w["adx"]
            desc = f"ADX {adx_val:.1f} — Trend zayıf / yatay piyasa"
        total += pts
        indicators.append({"name": "ADX", "value": f"{adx_val:.1f}",
                           "threshold": ">25 güçlü", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    vol_series = calc_volatility(close)
    if vol_series is not None and len(vol_series.dropna()) > 0:
        vol_now = vol_series.dropna().iloc[-1]
        vol_prev = vol_series.dropna().iloc[-22] if len(vol_series.dropna()) >= 22 else vol_now
        if vol_now < vol_prev * 0.9:
            pts = 1 * w["volatility"]
            desc = f"Volatilite %{vol_now:.1f} (düşüyor) — Sakin piyasa"
        elif vol_now > vol_prev * 1.2:
            pts = -1 * w["volatility"]
            desc = f"Volatilite %{vol_now:.1f} (yükseliyor) — Artan risk"
        else:
            pts = 0
            desc = f"Volatilite %{vol_now:.1f} — Stabil"
        total += pts
        indicators.append({"name": "Volatilite", "value": f"%{vol_now:.1f}",
                           "threshold": f"Önceki: %{vol_prev:.1f}", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible


def score_bist_money_flow(hist, usdtry_hist=None, cds_value=None, cds_trend=None,
                          bist_usd_above=None, yabanci_oran=None, yabanci_degisim=None):
    """Para akışı katmanı — CDS, döviz, hacim ve yabancı akımı"""
    w = BIST_WEIGHTS["money_flow"]
    indicators = []
    total = 0

    # CDS seviye sinyali
    if cds_value is not None:
        if cds_value < 200:
            pts = 1 * w["cds_signal"]
            desc = f"CDS {cds_value:.0f} bps — güçlü para girişi sinyali"
        elif cds_value < 300:
            pts = 0.5 * w["cds_signal"]
            desc = f"CDS {cds_value:.0f} bps — ılımlı para girişi"
        elif cds_value < 400:
            pts = -0.5 * w["cds_signal"]
            desc = f"CDS {cds_value:.0f} bps — para çıkışı riski"
        else:
            pts = -1 * w["cds_signal"]
            desc = f"CDS {cds_value:.0f} bps — sert para çıkışı"
        total += pts
        indicators.append({"name": "CDS Para Akışı", "value": f"{cds_value:.0f} bps",
                           "threshold": "<200/300/400", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # CDS trend
    if cds_trend is not None:
        if cds_trend == "falling":
            pts = 1 * w["cds_trend"]
            desc = "CDS düşüyor — para girişi artıyor"
        elif cds_trend == "rising":
            pts = -1 * w["cds_trend"]
            desc = "CDS yükseliyor — para çıkışı riski"
        else:
            pts = 0
            desc = "CDS yatay — nötr akış"
        total += pts
        indicators.append({"name": "CDS Akış Trendi", "value": cds_trend.capitalize() if cds_trend else "N/A",
                           "threshold": "5G trend", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # USDTRY değişim
    if usdtry_hist is not None and not usdtry_hist.empty and "Close" in usdtry_hist.columns:
        usdtry_close = usdtry_hist["Close"]
        if len(usdtry_close) >= 6:
            usdtry_change = (usdtry_close.iloc[-1] / usdtry_close.iloc[-6] - 1) * 100
            if usdtry_change < -0.5:
                pts = 1 * w["usdtry_change"]
                desc = f"USDTRY 5G {usdtry_change:+.2f}% — TL güçleniyor, para girişi"
            elif usdtry_change > 1.0:
                pts = -1 * w["usdtry_change"]
                desc = f"USDTRY 5G {usdtry_change:+.2f}% — TL zayıflıyor, para çıkışı"
            else:
                pts = 0
                desc = f"USDTRY 5G {usdtry_change:+.2f}% — stabil"
            total += pts
            indicators.append({"name": "USDTRY Değişim", "value": f"{usdtry_change:+.2f}%",
                               "threshold": "<-0.5%/>1%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

        # USDTRY volatilite
        usdtry_vol_current, usdtry_vol_avg = calc_usdtry_volatility(usdtry_close)
        if usdtry_vol_current is not None and usdtry_vol_avg is not None:
            if usdtry_vol_current < usdtry_vol_avg * 0.8:
                pts = 1 * w["usdtry_vol"]
                desc = f"USDTRY vol %{usdtry_vol_current:.1f} — düşük, stabil ortam"
            elif usdtry_vol_current > usdtry_vol_avg * 1.3:
                pts = -1 * w["usdtry_vol"]
                desc = f"USDTRY vol %{usdtry_vol_current:.1f} — yüksek, belirsizlik"
            else:
                pts = 0
                desc = f"USDTRY vol %{usdtry_vol_current:.1f} — normal"
            total += pts
            indicators.append({"name": "USDTRY Volatilite", "value": f"%{usdtry_vol_current:.1f}",
                               "threshold": f"Ort: %{usdtry_vol_avg:.1f}", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

    # BIST kısa vadeli trend (ROC)
    if hist is not None and not hist.empty:
        close = hist["Close"]
        roc = calc_roc(close, 10)
        if roc is not None and len(roc.dropna()) > 0:
            roc_val = roc.dropna().iloc[-1]
            if roc_val > 3:
                pts = 1 * w["bist_trend"]
                desc = f"BIST 10G ROC {roc_val:+.1f}% — güçlü yükseliş trendi"
            elif roc_val < -3:
                pts = -1 * w["bist_trend"]
                desc = f"BIST 10G ROC {roc_val:+.1f}% — düşüş trendi"
            else:
                pts = 0
                desc = f"BIST 10G ROC {roc_val:+.1f}% — yatay"
            total += pts
            indicators.append({"name": "BIST Trend (ROC)", "value": f"{roc_val:+.1f}%",
                               "threshold": ">3%/<-3%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                               "points": pts, "desc": desc})

        # Hacim gücü
        volume = hist["Volume"] if "Volume" in hist.columns else None
        if volume is not None:
            vol_sma20 = volume.rolling(20).mean()
            if len(vol_sma20.dropna()) > 0:
                last_vol = volume.iloc[-1]
                avg_vol = vol_sma20.dropna().iloc[-1]
                if last_vol > avg_vol * 1.2:
                    pts = 1 * w["volume_strength"]
                    desc = f"Hacim ortalamanın %{last_vol/avg_vol*100:.0f}'ı — güçlü katılım"
                elif last_vol < avg_vol * 0.7:
                    pts = -1 * w["volume_strength"]
                    desc = f"Hacim ortalamanın %{last_vol/avg_vol*100:.0f}'ı — zayıf katılım"
                else:
                    pts = 0
                    desc = "Hacim normal seviyede"
                total += pts
                indicators.append({"name": "Hacim Gücü", "value": f"{last_vol:,.0f}",
                                   "threshold": f"SMA20: {avg_vol:,.0f}", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                                   "points": pts, "desc": desc})

    # BIST/USD trend
    if bist_usd_above is not None:
        if bist_usd_above:
            pts = 1 * w["bist_usd"]
            desc = "BIST/USD SMA200 üzerinde — dolar bazlı para girişi"
        else:
            pts = -1 * w["bist_usd"]
            desc = "BIST/USD SMA200 altında — dolar bazlı para çıkışı"
        total += pts
        indicators.append({"name": "BIST/USD Akış", "value": "Üzeri" if bist_usd_above else "Altı",
                           "threshold": "SMA200", "signal": 1 if bist_usd_above else -1,
                           "points": pts, "desc": desc})

    # Yabancı oran/değişim
    if yabanci_oran is not None and yabanci_degisim is not None:
        if yabanci_degisim > 1.5:
            pts = 1 * w["foreign_ratio"]
            desc = f"Yabancı payı %{yabanci_oran:.1f} (+{yabanci_degisim:.1f}pp) — yabancı alımda"
        elif yabanci_degisim < -1.5:
            pts = -1 * w["foreign_ratio"]
            desc = f"Yabancı payı %{yabanci_oran:.1f} ({yabanci_degisim:.1f}pp) — yabancı satışta"
        else:
            pts = 0
            desc = f"Yabancı payı %{yabanci_oran:.1f} — yatay"
        total += pts
        indicators.append({"name": "Yabancı Akışı", "value": f"%{yabanci_oran:.1f}",
                           "threshold": f"Δ: {yabanci_degisim:+.1f}pp", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible


def score_bist_momentum(hist):
    """Momentum katmanı — RSI, MACD, ROC, volatilite rejimi"""
    w = BIST_WEIGHTS["momentum"]
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
            desc = f"RSI {rsi_val:.1f} — aşırı alım, momentum zayıflayabilir"
        elif rsi_val < RSI_THRESHOLDS["oversold"]:
            pts = -0.5 * w["rsi"]
            desc = f"RSI {rsi_val:.1f} — aşırı satım, toparlanma beklenebilir"
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
            desc = f"MACD histogram pozitif ({mh:.1f}) — yukarı momentum"
        else:
            pts = -1 * w["macd"]
            desc = f"MACD histogram negatif ({mh:.1f}) — aşağı momentum"
        total += pts
        indicators.append({"name": "MACD Momentum", "value": f"{mh:.1f}",
                           "threshold": ">0/<0", "signal": 1 if mh > 0 else -1,
                           "points": pts, "desc": desc})

    # ROC
    roc = calc_roc(close, 10)
    if roc is not None and len(roc.dropna()) > 0:
        roc_val = roc.dropna().iloc[-1]
        if roc_val > 3:
            pts = 1 * w["roc"]
            desc = f"ROC 10G {roc_val:+.1f}% — güçlü momentum"
        elif roc_val < -3:
            pts = -1 * w["roc"]
            desc = f"ROC 10G {roc_val:+.1f}% — zayıf momentum"
        else:
            pts = 0
            desc = f"ROC 10G {roc_val:+.1f}% — nötr"
        total += pts
        indicators.append({"name": "ROC (10G)", "value": f"{roc_val:+.1f}%",
                           "threshold": ">3%/<-3%", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    # Volatilite rejimi
    vol = calc_volatility(close)
    if vol is not None and len(vol.dropna()) >= 2:
        vol_now = vol.dropna().iloc[-1]
        vol_prev = vol.dropna().iloc[-6] if len(vol.dropna()) >= 6 else vol.dropna().iloc[0]
        vol_falling = vol_now < vol_prev
        roc_positive = roc is not None and len(roc.dropna()) > 0 and roc.dropna().iloc[-1] > 0
        if vol_falling and roc_positive:
            pts = 1 * w["vol_regime"]
            desc = f"Vol düşüyor ({vol_now:.1f}%) + momentum pozitif — güçlü rejim"
        elif not vol_falling and not roc_positive:
            pts = -1 * w["vol_regime"]
            desc = f"Vol yükseliyor ({vol_now:.1f}%) + momentum negatif — zayıf rejim"
        else:
            pts = 0
            desc = f"Volatilite rejimi karışık ({vol_now:.1f}%)"
        total += pts
        indicators.append({"name": "Volatilite Rejimi", "value": f"%{vol_now:.1f}",
                           "threshold": "Vol↓ + Mom↑", "signal": 1 if pts > 0 else (-1 if pts < 0 else 0),
                           "points": pts, "desc": desc})

    max_possible = sum(abs(v) for v in w.values()) * 2
    return total, indicators, max_possible

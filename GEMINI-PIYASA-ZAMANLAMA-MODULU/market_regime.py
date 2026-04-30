def detect_regime_bist(macro_score, breadth_pct, volatility, cds_value):
    crisis_override = False
    if cds_value is not None and cds_value > 500:
        crisis_override = True

    if crisis_override:
        return "crisis", "CDS > 500 bps — Ülke riski kriz seviyesinde"

    signals = 0
    if macro_score is not None:
        if macro_score > 3:
            signals += 2
        elif macro_score > 0:
            signals += 1
        elif macro_score < -3:
            signals -= 2
        else:
            signals -= 1

    if breadth_pct is not None:
        if breadth_pct > 60:
            signals += 1
        elif breadth_pct < 30:
            signals -= 1

    if volatility is not None:
        if volatility > 35:
            signals -= 1
        elif volatility < 20:
            signals += 1

    if signals >= 3:
        return "risk_on", "Makro ortam güçlü, piyasa genişliği sağlıklı, volatilite kontrollü"
    elif signals >= 1:
        return "neutral", "Karışık sinyaller — bazı göstergeler pozitif, bazıları nötr"
    elif signals >= -1:
        return "risk_off", "Makro baskı altında, piyasa genişliği zayıflıyor"
    else:
        return "crisis", "Çoklu negatif sinyal — makro, breadth ve volatilite olumsuz"


def detect_regime_usa(vix, breadth_pct, treasury_yield, dxy_strong, sma200_above):
    if vix is not None and vix > 30:
        return "crisis", f"VIX {vix:.1f} — Piyasa paniği"
    if vix is not None and vix > 25:
        return "risk_off", f"VIX {vix:.1f} — Yüksek korku ortamı"

    signals = 0

    if sma200_above:
        signals += 1
    elif sma200_above is not None:
        signals -= 1

    if breadth_pct is not None:
        if breadth_pct > 60:
            signals += 1
        elif breadth_pct < 35:
            signals -= 1

    if vix is not None:
        if vix < 15:
            signals += 1
        elif vix > 20:
            signals -= 1

    if treasury_yield is not None:
        if treasury_yield > 4.5:
            signals -= 1
        elif treasury_yield < 3.5:
            signals += 1

    if dxy_strong:
        signals -= 1
    elif dxy_strong is not None and not dxy_strong:
        signals += 1

    if signals >= 3:
        return "risk_on", "VIX düşük, trend güçlü, breadth sağlıklı"
    elif signals >= 1:
        return "neutral", "Sinyaller karışık, bazı risk faktörleri mevcut"
    elif signals >= -1:
        return "risk_off", "Trend zayıflıyor, risk göstergeleri bozuluyor"
    else:
        return "crisis", "Çoklu negatif sinyal — trend, breadth ve risk göstergeleri olumsuz"

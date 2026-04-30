# 5-katman ağırlıkları
BIST_LAYER_WEIGHTS = {
    "macro": 0.35,
    "money_flow": 0.25,
    "breadth": 0.15,
    "technical": 0.15,
    "momentum": 0.10,
}

USA_LAYER_WEIGHTS = {
    "risk": 0.30,
    "breadth": 0.25,
    "technical": 0.20,
    "momentum": 0.15,
    "sentiment": 0.10,
}

SCORE_SCALE = 10

BIST_DECISION_THRESHOLDS = {
    "uygun": 3.0,
    "kademeli": 1.0,
    "dikkatli": -0.5,
    "bekle": -3.0,
}

USA_DECISION_THRESHOLDS = {
    "agresif": 3.0,
    "kademeli": 1.5,
    "notr": -0.5,
}

BIST_WEIGHTS = {
    "macro": {
        "cds": 3,
        "real_rate": 2,
        "bist_usd": 2,
        "usdtry_vol": 2,
        "foreign_flow": 1,
    },
    "health": {
        "breadth_sma50": 2,
        "breadth_sma200": 1,
        "new_high_low": 1,
        "volume_obv": 2,
        "sector_leadership": 1,
    },
    "timing": {
        "sma_position": 2,
        "sma50_slope": 1,
        "sma200_slope": 1,
        "rsi": 0,
        "macd": 0,
        "adx": 1,
        "volatility": 1,
    },
    "money_flow": {
        "cds_signal": 2,
        "cds_trend": 1,
        "usdtry_change": 2,
        "usdtry_vol": 1,
        "bist_trend": 2,
        "volume_strength": 1,
        "bist_usd": 2,
        "foreign_ratio": 1,
    },
    "momentum": {
        "rsi": 1,
        "macd": 1,
        "roc": 1,
        "vol_regime": 1,
    },
}

USA_WEIGHTS = {
    "risk": {
        "vix": 3,
        "treasury_10y": 2,
        "dxy": 2,
        "credit_spread": 1,
        "yield_curve": 1,
        "liquidity": 1,
    },
    "internals": {
        "breadth_sma50": 2,
        "breadth_sma200": 1,
        "new_high_low": 1,
        "equal_vs_cap": 1,
        "relative_strength": 1,
        "put_call": 0,
    },
    "timing": {
        "sma_position": 2,
        "sma50_slope": 1,
        "macd": 0,
        "rsi": 0,
        "volume": 1,
    },
    "momentum": {
        "rsi": 1,
        "macd": 1,
        "roc": 1,
        "qqq_spy": 1,
        "iwm_spy": 1,
    },
    "sentiment": {
        "put_call": 2,
        "volume_quality": 1,
        "liquidity": 1,
    },
}

CDS_THRESHOLDS = {
    "guclu_giris": 200,
    "ilimli_giris": 300,
    "zayif_ilgi": 400,
    "sert_cikis": 500,
}

VIX_THRESHOLDS = {
    "safe": 15,
    "caution": 25,
}

TREASURY_THRESHOLDS = {
    "positive": 3.5,
    "negative": 4.5,
}

RSI_THRESHOLDS = {
    "oversold": 35,
    "healthy_low": 45,
    "healthy_high": 65,
    "overbought": 70,
}

RISK_PROFILES = {
    "Korumacı": {
        "threshold_shift": 1,
        "label": "Korumacı",
        "desc": "Daha düşük risk toleransı, sinyallerde temkinli",
        "weight_multipliers": {"macro": 1.3, "health": 1.0, "timing": 0.7, "money_flow": 1.2, "breadth": 1.0, "technical": 0.7, "momentum": 0.7, "sentiment": 1.0},
        "allocations": {
            "UYGUN":          {"hisse": 50, "tahvil": 30, "nakit": 20},
            "AGRESİF ALIM UYGUN": {"hisse": 50, "tahvil": 30, "nakit": 20},
            "KADEMELİ ALIM":  {"hisse": 30, "tahvil": 40, "nakit": 30},
            "KADEMELİ / DİKKATLİ İŞLEM": {"hisse": 30, "tahvil": 40, "nakit": 30},
            "DİKKATLİ":       {"hisse": 20, "tahvil": 40, "nakit": 40},
            "NÖTR / BEKLE":   {"hisse": 10, "tahvil": 40, "nakit": 50},
            "BEKLE":          {"hisse": 10, "tahvil": 40, "nakit": 50},
            "GİRMEYİN":       {"hisse": 0,  "tahvil": 30, "nakit": 70},
            "GİRMEYİN / KORUMACI MOD": {"hisse": 0, "tahvil": 30, "nakit": 70},
            "RİSKLİ / BEKLE": {"hisse": 0,  "tahvil": 20, "nakit": 80},
            "RİSKLİ / NAKİTTE BEKLE": {"hisse": 0, "tahvil": 20, "nakit": 80},
        },
        "stop_loss": {
            "UYGUN":          {"tip": "SMA50 altı", "yuzde": 5},
            "AGRESİF ALIM UYGUN": {"tip": "SMA50 altı", "yuzde": 5},
            "KADEMELİ ALIM":  {"tip": "Son 20G dip altı", "yuzde": 4},
            "KADEMELİ / DİKKATLİ İŞLEM": {"tip": "Son 20G dip altı", "yuzde": 4},
            "DİKKATLİ":       {"tip": "Giriş fiyatı altı", "yuzde": 3},
        },
    },
    "Dengeli": {
        "threshold_shift": 0,
        "label": "Dengeli",
        "desc": "Standart sinyal değerlendirmesi",
        "weight_multipliers": {"macro": 1.0, "health": 1.0, "timing": 1.0, "money_flow": 1.0, "breadth": 1.0, "technical": 1.0, "momentum": 1.0, "sentiment": 1.0},
        "allocations": {
            "UYGUN":          {"hisse": 70, "tahvil": 20, "nakit": 10},
            "AGRESİF ALIM UYGUN": {"hisse": 70, "tahvil": 20, "nakit": 10},
            "KADEMELİ ALIM":  {"hisse": 50, "tahvil": 30, "nakit": 20},
            "KADEMELİ / DİKKATLİ İŞLEM": {"hisse": 50, "tahvil": 30, "nakit": 20},
            "DİKKATLİ":       {"hisse": 30, "tahvil": 35, "nakit": 35},
            "NÖTR / BEKLE":   {"hisse": 20, "tahvil": 35, "nakit": 45},
            "BEKLE":          {"hisse": 20, "tahvil": 35, "nakit": 45},
            "GİRMEYİN":       {"hisse": 0,  "tahvil": 40, "nakit": 60},
            "GİRMEYİN / KORUMACI MOD": {"hisse": 0, "tahvil": 40, "nakit": 60},
            "RİSKLİ / BEKLE": {"hisse": 0,  "tahvil": 20, "nakit": 80},
            "RİSKLİ / NAKİTTE BEKLE": {"hisse": 0, "tahvil": 20, "nakit": 80},
        },
        "stop_loss": {
            "UYGUN":          {"tip": "SMA50 altı", "yuzde": 7},
            "AGRESİF ALIM UYGUN": {"tip": "SMA50 altı", "yuzde": 7},
            "KADEMELİ ALIM":  {"tip": "Son 20G dip altı", "yuzde": 5},
            "KADEMELİ / DİKKATLİ İŞLEM": {"tip": "Son 20G dip altı", "yuzde": 5},
            "DİKKATLİ":       {"tip": "Giriş fiyatı altı", "yuzde": 4},
        },
    },
    "Fırsatçı": {
        "threshold_shift": 0,
        "label": "Fırsatçı",
        "desc": "Piyasa bekleme sinyalinde bile seçici hisselerle kısmi pozisyon — sıkı stop-loss zorunlu",
        "weight_multipliers": {"macro": 0.5, "health": 1.0, "timing": 1.5, "money_flow": 0.6, "breadth": 1.0, "technical": 1.5, "momentum": 1.5, "sentiment": 0.7},
        "allocations": {
            "UYGUN":          {"hisse": 80, "tahvil": 10, "nakit": 10},
            "AGRESİF ALIM UYGUN": {"hisse": 80, "tahvil": 10, "nakit": 10},
            "KADEMELİ ALIM":  {"hisse": 60, "tahvil": 20, "nakit": 20},
            "KADEMELİ / DİKKATLİ İŞLEM": {"hisse": 60, "tahvil": 20, "nakit": 20},
            "DİKKATLİ":       {"hisse": 40, "tahvil": 20, "nakit": 40},
            "NÖTR / BEKLE":   {"hisse": 25, "tahvil": 15, "nakit": 60},
            "BEKLE":          {"hisse": 25, "tahvil": 15, "nakit": 60},
            "GİRMEYİN":       {"hisse": 20, "tahvil": 10, "nakit": 70},
            "GİRMEYİN / KORUMACI MOD": {"hisse": 20, "tahvil": 10, "nakit": 70},
            "RİSKLİ / BEKLE": {"hisse": 10, "tahvil": 10, "nakit": 80},
            "RİSKLİ / NAKİTTE BEKLE": {"hisse": 10, "tahvil": 10, "nakit": 80},
        },
        "stop_loss": {
            "UYGUN":          {"tip": "SMA50 altı", "yuzde": 7},
            "AGRESİF ALIM UYGUN": {"tip": "SMA50 altı", "yuzde": 7},
            "KADEMELİ ALIM":  {"tip": "Son 20G dip altı", "yuzde": 5},
            "KADEMELİ / DİKKATLİ İŞLEM": {"tip": "Son 20G dip altı", "yuzde": 5},
            "DİKKATLİ":       {"tip": "Giriş fiyatı altı", "yuzde": 4},
            "NÖTR / BEKLE":   {"tip": "Giriş fiyatı altı", "yuzde": 3},
            "BEKLE":          {"tip": "Giriş fiyatı altı", "yuzde": 3},
            "GİRMEYİN":       {"tip": "Giriş fiyatı altı", "yuzde": 3},
            "GİRMEYİN / KORUMACI MOD": {"tip": "Giriş fiyatı altı", "yuzde": 3},
        },
        "selective_note": {
            "BEKLE":          "⚡ Nakitin %25\'i ile yalnızca güçlü timing sinyali veren seçici hisseler — sıkı stop-loss zorunlu",
            "GİRMEYİN":       "⚡ Nakitin %20\'si ile yalnızca teknik olarak öne çıkan hisseler — pozisyon başına max %3 risk",
            "GİRMEYİN / KORUMACI MOD": "⚡ Nakitin %20\'si ile yalnızca teknik olarak öne çıkan hisseler — pozisyon başına max %3 risk",
            "RİSKLİ / BEKLE": "⚠️ Nakitin %10\'u, çok seçici — zarar durumunda hemen çık",
            "RİSKLİ / NAKİTTE BEKLE": "⚠️ Nakitin %10\'u, çok seçici — zarar durumunda hemen çık",
        },
    },
    "Agresif": {
        "threshold_shift": -1,
        "label": "Agresif",
        "desc": "Daha yüksek risk toleransı, erken giriş",
        "weight_multipliers": {"macro": 0.7, "health": 1.0, "timing": 1.3, "money_flow": 0.8, "breadth": 1.0, "technical": 1.3, "momentum": 1.3, "sentiment": 0.8},
        "allocations": {
            "UYGUN":          {"hisse": 90, "tahvil": 5,  "nakit": 5},
            "AGRESİF ALIM UYGUN": {"hisse": 90, "tahvil": 5, "nakit": 5},
            "KADEMELİ ALIM":  {"hisse": 70, "tahvil": 15, "nakit": 15},
            "KADEMELİ / DİKKATLİ İŞLEM": {"hisse": 70, "tahvil": 15, "nakit": 15},
            "DİKKATLİ":       {"hisse": 50, "tahvil": 25, "nakit": 25},
            "NÖTR / BEKLE":   {"hisse": 30, "tahvil": 30, "nakit": 40},
            "BEKLE":          {"hisse": 30, "tahvil": 30, "nakit": 40},
            "GİRMEYİN":       {"hisse": 10, "tahvil": 30, "nakit": 60},
            "GİRMEYİN / KORUMACI MOD": {"hisse": 10, "tahvil": 30, "nakit": 60},
            "RİSKLİ / BEKLE": {"hisse": 0,  "tahvil": 30, "nakit": 70},
            "RİSKLİ / NAKİTTE BEKLE": {"hisse": 0, "tahvil": 30, "nakit": 70},
        },
        "stop_loss": {
            "UYGUN":          {"tip": "SMA200 altı", "yuzde": 10},
            "AGRESİF ALIM UYGUN": {"tip": "SMA200 altı", "yuzde": 10},
            "KADEMELİ ALIM":  {"tip": "SMA50 altı", "yuzde": 7},
            "KADEMELİ / DİKKATLİ İŞLEM": {"tip": "SMA50 altı", "yuzde": 7},
            "DİKKATLİ":       {"tip": "Son 20G dip altı", "yuzde": 5},
        },
    },
}

REGIME_LABELS = {
    "risk_on": {"label": "Risk-On", "color": "#10B981", "icon": "🟢"},
    "neutral": {"label": "Nötr", "color": "#F59E0B", "icon": "🟡"},
    "risk_off": {"label": "Risk-Off", "color": "#EF4444", "icon": "🔴"},
    "crisis": {"label": "Kriz", "color": "#7F1D1D", "icon": "⛔"},
}

VERDICT_MAP = {
    "UYGUN": {"color": "#10B981", "bg": "#ECFDF5", "border": "#6EE7B7", "icon": "✅"},
    "AGRESİF ALIM UYGUN": {"color": "#10B981", "bg": "#ECFDF5", "border": "#6EE7B7", "icon": "✅"},
    "DİKKATLİ": {"color": "#F59E0B", "bg": "#FFFBEB", "border": "#FCD34D", "icon": "⚠️"},
    "KADEMELİ / DİKKATLİ İŞLEM": {"color": "#F59E0B", "bg": "#FFFBEB", "border": "#FCD34D", "icon": "⚠️"},
    "KADEMELİ ALIM": {"color": "#F59E0B", "bg": "#FFFBEB", "border": "#FCD34D", "icon": "⚠️"},
    "NÖTR / BEKLE": {"color": "#6B7280", "bg": "#F3F4F6", "border": "#D1D5DB", "icon": "⏸️"},
    "BEKLE": {"color": "#6B7280", "bg": "#F3F4F6", "border": "#D1D5DB", "icon": "⏸️"},
    "GİRMEYİN": {"color": "#EF4444", "bg": "#FEF2F2", "border": "#FCA5A5", "icon": "🛑"},
    "GİRMEYİN / KORUMACI MOD": {"color": "#EF4444", "bg": "#FEF2F2", "border": "#FCA5A5", "icon": "🛑"},
    "RİSKLİ / BEKLE": {"color": "#EF4444", "bg": "#FEF2F2", "border": "#FCA5A5", "icon": "🛑"},
    "RİSKLİ / NAKİTTE BEKLE": {"color": "#EF4444", "bg": "#FEF2F2", "border": "#FCA5A5", "icon": "🛑"},
}

BIST_TICKERS = [
    "THYAO.IS", "ASELS.IS", "GARAN.IS", "AKBNK.IS", "EREGL.IS", "TUPRS.IS",
    "SAHOL.IS", "KCHOL.IS", "BIMAS.IS", "SISE.IS", "TOASO.IS", "FROTO.IS",
    "PGSUS.IS", "TCELL.IS", "HEKTS.IS", "PETKM.IS", "ARCLK.IS", "ENKAI.IS",
    "TAVHL.IS", "GUBRF.IS", "ISCTR.IS", "YKBNK.IS", "VAKBN.IS", "HALKB.IS",
    "DOHOL.IS", "TTKOM.IS", "EKGYO.IS", "MGROS.IS", "OTKAR.IS", "KRDMD.IS",
    "SASA.IS", "KONTR.IS", "AKSEN.IS", "TTRAK.IS", "VESTL.IS", "GESAN.IS",
    "OYAKC.IS", "CIMSA.IS", "AEFES.IS", "ULKER.IS", "ISGYO.IS",
    "DOAS.IS", "BRISA.IS", "ALARK.IS", "ENJSA.IS", "AGHOL.IS", "SKBNK.IS",
    "TMSN.IS", "MPARK.IS", "BRYAT.IS", "CCOLA.IS", "ANHYT.IS", "ANSGR.IS",
    "LOGO.IS", "NETAS.IS", "SOKM.IS", "AKSA.IS", "KORDS.IS", "TKFEN.IS",
    "CANTE.IS", "MAVI.IS", "TKNSA.IS", "KLRHO.IS", "ISMEN.IS", "ALBRK.IS",
    "IPEKE.IS", "TRGYO.IS", "PRKME.IS", "QUAGR.IS", "YEOTK.IS", "BERA.IS",
    "KMPUR.IS", "BTCIM.IS", "CEMAS.IS", "GEDZA.IS", "GLYHO.IS", "OZKGY.IS",
    "AYDEM.IS", "KARSN.IS", "TURSG.IS", "ODAS.IS", "BUCIM.IS", "POLHO.IS",
    "VERTU.IS", "CWENE.IS", "BOBET.IS", "KCAER.IS", "EUPWR.IS", "REEDR.IS",
    "ALFAS.IS", "ARDYZ.IS", "OBAMS.IS", "RGYAS.IS", "KAYSE.IS", "BIOEN.IS",
]

BIST_SECTOR_MAP = {
    "banks": ["GARAN.IS", "AKBNK.IS", "ISCTR.IS", "YKBNK.IS", "VAKBN.IS", "HALKB.IS", "SKBNK.IS", "ALBRK.IS"],
    "industrials": ["EREGL.IS", "TOASO.IS", "FROTO.IS", "ARCLK.IS", "VESTL.IS", "KRDMD.IS", "SASA.IS", "BRISA.IS"],
    "holdings": ["SAHOL.IS", "KCHOL.IS", "DOHOL.IS", "AGHOL.IS", "GLYHO.IS", "POLHO.IS"],
    "energy": ["TUPRS.IS", "AKSEN.IS", "ENJSA.IS", "AYDEM.IS", "ODAS.IS", "CWENE.IS"],
}

SP500_TICKERS = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "BRK-B", "UNH", "XOM", "JPM",
    "JNJ", "V", "PG", "MA", "AVGO", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "COST", "ADBE", "WMT", "MCD", "CRM", "TMO", "CSCO", "ACN",
    "ABT", "DHR", "NKE", "NEE", "TXN", "PM", "UNP", "RTX", "INTC", "AMD",
    "HON", "AMGN", "LOW", "UPS", "QCOM", "IBM", "BA", "CAT", "GE", "SPGI",
    "INTU", "BLK", "AMAT", "ISRG", "GILD", "SYK", "ADP", "MDLZ", "BKNG", "ADI",
    "GS", "VRTX", "REGN", "TJX", "MMC", "LRCX", "SBUX", "PGR", "ETN", "ZTS",
    "C", "SCHW", "BDX", "CB", "SO", "MO", "DUK", "CME", "CL", "CI",
    "PNC", "USB", "TFC", "NSC", "ITW", "FDX", "SHW", "AON", "KLAC", "SNPS",
    "MCK", "APD", "AIG", "ECL", "EMR", "GM", "F", "SLB", "PSX", "VLO",
    "WBA", "KMB", "D", "AEP", "EXC", "XEL", "WEC", "ES", "AEE", "CMS",
    "WELL", "ARE", "DLR", "PSA", "O", "SPG", "AMT", "PLD", "EQIX", "CCI",
    "AFL", "MET", "PRU", "TRV", "ALL", "HIG", "L", "AJG", "MMM", "DD",
    "DOW", "LIN", "APH", "CDNS", "MCHP", "FTNT", "PANW", "NXPI", "ON", "SWKS",
    "WM", "RSG", "VRSK", "CTAS", "PAYX", "CPRT", "FAST", "ODFL", "JBHT", "CHRW",
    "MSCI", "ICE", "NDAQ", "CBOE", "CMG", "YUM", "DRI", "SYY", "HLT", "MAR",
    "LUV", "DAL", "UAL", "AAL", "ABNB", "RCL", "CCL", "NCLH", "WYNN", "LVS",
    "DHI", "LEN", "PHM", "NVR", "TOL", "TSLA", "RIVN", "LCID", "NIO", "XPEV",
    "DIS", "CMCSA", "NFLX", "PARA", "WBD", "FOX", "T", "VZ", "TMUS", "CHTR",
    "PFE", "BMY", "MRNA", "ZBH", "EW", "BSX", "MDT", "DXCM", "IDXX", "A",
    "CVS", "HCA", "CNC", "ELV", "HUM", "MOH", "BIIB", "ILMN", "ALGN", "HOLX",
    "DE", "PCAR", "CMI", "PH", "ROK", "AME", "GWW", "SWK", "IR", "OTIS",
    "CARR", "JCI", "TT", "LII", "AOS", "SNA", "ROP", "IEX", "KEYS", "TER",
    "KHC", "GIS", "CAG", "SJM", "CPB", "HRL", "MKC", "K", "HSY", "MNST",
    "STZ", "TAP", "BF-B", "SAM", "EL", "CLX", "CHD", "CG", "KKR", "BX",
    "ARES", "APO", "OWL", "BAM", "COIN", "HOOD", "SOFI", "SQ", "PYPL", "FIS",
    "FISV", "GPN", "WEX", "DFS", "AXP", "COF", "SYF", "ALLY", "NTRS", "STT",
    "BK", "CFG", "RF", "HBAN", "KEY", "ZION", "FHN", "CMA", "WBS", "MTB",
    "FITB", "CINF", "ERIE", "RNR", "WRB", "ACGL", "EG", "BRO", "AON", "WTW",
]

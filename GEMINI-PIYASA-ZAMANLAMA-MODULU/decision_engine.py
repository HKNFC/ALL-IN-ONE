from config import VERDICT_MAP, RISK_PROFILES


def apply_weight_multipliers(layer1_score, layer2_score, timing_score, profile,
                             layer1_key="macro", layer2_key="health"):
    mults = profile.get("weight_multipliers", {})
    return (
        layer1_score * mults.get(layer1_key, mults.get("macro", 1.0)),
        layer2_score * mults.get(layer2_key, mults.get("health", 1.0)),
        timing_score * mults.get("timing", 1.0),
    )


def get_allocation(verdict, profile):
    allocs = profile.get("allocations", {})
    return allocs.get(verdict, {"hisse": 0, "tahvil": 30, "nakit": 70})


def get_stop_loss(verdict, profile):
    stops = profile.get("stop_loss", {})
    return stops.get(verdict, None)


def decide_bist(macro_score, health_score, timing_score, regime, cds_value, real_rate,
                breadth_pct, bist_usd_above, risk_profile="Dengeli", cds_trend=None,
                yabanci_oran=None, yabanci_degisim=None):
    profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["Dengeli"])
    shift = profile["threshold_shift"]

    adj_macro, adj_health, adj_timing = apply_weight_multipliers(
        macro_score, health_score, timing_score, profile
    )

    if cds_trend == "rising":
        adj_timing *= 0.7
    elif cds_trend == "falling":
        adj_timing *= 1.3

    total = adj_macro + adj_health + adj_timing

    yab_kwargs = dict(yabanci_oran=yabanci_oran, yabanci_degisim=yabanci_degisim)

    if cds_value is not None and cds_value > 500:
        verdict = "RİSKLİ / BEKLE"
        explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                                regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    if regime == "crisis":
        verdict = "RİSKLİ / BEKLE"
        explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                                regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    if (bist_usd_above is not None and not bist_usd_above and
        real_rate is not None and real_rate > 3 and
        breadth_pct is not None and breadth_pct < 40):
        verdict = "GİRMEYİN"
        explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                                regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    threshold_uygun = 5 + shift
    threshold_dikkatli = 1 + shift
    threshold_kademe = -2 + shift

    if total >= threshold_uygun and adj_macro > 0:
        verdict = "UYGUN"
    elif total >= threshold_dikkatli:
        if adj_macro < -2:
            verdict = "DİKKATLİ"
        else:
            verdict = "KADEMELİ ALIM"
    elif total >= threshold_kademe:
        verdict = "DİKKATLİ"
    elif total > -5 + shift:
        verdict = "BEKLE"
    else:
        verdict = "GİRMEYİN"

    if adj_macro < -3 and adj_timing > 2:
        verdict = "DİKKATLİ"

    explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                            regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
    alloc = get_allocation(verdict, profile)
    stop = get_stop_loss(verdict, profile)
    return verdict, total, explanation, alloc, stop


def decide_usa(risk_score, internals_score, timing_score, regime, vix, vix_rising,
               breadth_pct, sma200_above, risk_profile="Dengeli"):
    profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["Dengeli"])
    shift = profile["threshold_shift"]

    adj_risk, adj_internals, adj_timing = apply_weight_multipliers(
        risk_score, internals_score, timing_score, profile,
        layer1_key="macro", layer2_key="health",
    )
    total = adj_risk + adj_internals + adj_timing

    if vix is not None and vix > 25:
        verdict = "RİSKLİ / NAKİTTE BEKLE"
        explanation = generate_usa_explanation(verdict, risk_score, internals_score, timing_score,
                                               regime, vix, breadth_pct, total)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    if (sma200_above is not None and not sma200_above and
        breadth_pct is not None and breadth_pct < 35):
        verdict = "GİRMEYİN / KORUMACI MOD"
        explanation = generate_usa_explanation(verdict, risk_score, internals_score, timing_score,
                                               regime, vix, breadth_pct, total)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    threshold_agresif = 5 + shift
    threshold_kademe = 2 + shift
    threshold_notr = -1 + shift

    if total >= threshold_agresif:
        verdict = "AGRESİF ALIM UYGUN"
    elif total >= threshold_kademe:
        verdict = "KADEMELİ / DİKKATLİ İŞLEM"
    elif total >= threshold_notr:
        verdict = "NÖTR / BEKLE"
    else:
        verdict = "GİRMEYİN / KORUMACI MOD"

    explanation = generate_usa_explanation(verdict, risk_score, internals_score, timing_score,
                                           regime, vix, breadth_pct, total)
    alloc = get_allocation(verdict, profile)
    stop = get_stop_loss(verdict, profile)
    return verdict, total, explanation, alloc, stop


def generate_bist_explanation(verdict, macro, health, timing, regime, cds, real_rate, breadth,
                              cds_trend=None, yabanci_oran=None, yabanci_degisim=None):
    parts = []

    if regime == "crisis":
        parts.append("Piyasa rejimi KRİZ modunda.")
    elif regime == "risk_off":
        parts.append("Piyasa rejimi Risk-Off — savunmacı yaklaşım gerekiyor.")

    if cds is not None:
        if cds > 500:
            parts.append(f"CDS {cds:.0f} bps — sistem kapalı, tüm sinyaller geçersiz.")
        elif cds > 400:
            parts.append(f"CDS {cds:.0f} bps — yabancı sert çıkışta, piyasa baskı altında.")
        elif cds > 300:
            parts.append(f"CDS {cds:.0f} bps — yabancı ilgisi zayıf, çıkış riski var.")
        elif cds > 200:
            parts.append(f"CDS {cds:.0f} bps — yabancı ilgisi ılımlı.")
        else:
            parts.append(f"CDS {cds:.0f} bps — yabancı ilgisi güçlü, sermaye girişi olumlu.")

    if cds_trend == "rising":
        parts.append("CDS yükselme eğiliminde — risk artıyor, teknik sinyallerin gücü düşürüldü.")
    elif cds_trend == "falling":
        parts.append("CDS düşme eğiliminde — risk azalıyor, teknik sinyaller güçlendirildi.")

    if yabanci_oran is not None and yabanci_degisim is not None:
        if yabanci_degisim > 1.5:
            parts.append(f"Yabancı takas payı %{yabanci_oran:.1f} (+{yabanci_degisim:.1f}pp) — yabancı alım eğiliminde, piyasaya para girişi var.")
        elif yabanci_degisim < -1.5:
            parts.append(f"Yabancı takas payı %{yabanci_oran:.1f} ({yabanci_degisim:.1f}pp) — yabancı satış eğiliminde, sermaye çıkışı riski.")
        else:
            parts.append(f"Yabancı takas payı %{yabanci_oran:.1f} — eğilim yatay.")

    if macro > 2:
        parts.append("Makro görünüm güçlü.")
    elif macro < -2:
        parts.append("Makro ortam baskılı.")

    if health > 2:
        parts.append("Piyasa genişliği ve iç yapı sağlıklı.")
    elif health < -2:
        parts.append("Piyasa genişliği zayıf, dar liderlik var.")

    if timing > 2:
        parts.append("Teknik zamanlama olumlu.")
    elif timing < -2:
        parts.append("Teknik göstergeler zayıf.")
    elif timing > 0 and macro < 0:
        parts.append("Teknik toparlanıyor ama makro henüz desteklemiyor — sadece kısa vadeli dikkatli işlem.")

    if breadth is not None and breadth < 30:
        parts.append(f"SMA50 üzerindeki hisse oranı sadece %{breadth:.0f} — piyasa çok dar.")

    if real_rate is not None and real_rate > 5:
        parts.append(f"Reel faiz %{real_rate:.1f} ile yüksek — mevduat/tahvil alternatifi güçlü.")

    conclusions = {
        "UYGUN": "Genel görünüm olumlu, pozisyon alınabilir.",
        "KADEMELİ ALIM": "Kademeli giriş ve sıkı stop-loss ile işlem yapılabilir.",
        "DİKKATLİ": "Agresif giriş yerine dikkatli ve seçici yaklaşım önerilir.",
        "BEKLE": "Koşullar netleşene kadar beklemek mantıklı.",
        "GİRMEYİN": "Olumsuz sinyaller ağır basıyor, piyasadan uzak durun.",
        "RİSKLİ / BEKLE": "Override aktif — koşullar ne olursa olsun nakitte kalın.",
    }
    parts.append(conclusions.get(verdict, ""))

    return " ".join(parts)


def generate_usa_explanation(verdict, risk, internals, timing, regime, vix, breadth, total):
    parts = []

    if vix is not None and vix > 25:
        parts.append(f"VIX {vix:.1f} ile korku seviyesi yüksek — puan ({total:.0f}) ne olursa olsun override aktif.")
    elif vix is not None and vix < 15:
        parts.append(f"VIX {vix:.1f} ile düşük risk ortamı.")

    if regime in ("crisis", "risk_off"):
        parts.append(f"Piyasa rejimi {regime.upper().replace('_',' ')} — savunmacı yaklaşım gerekiyor.")

    if risk > 2:
        parts.append("Risk göstergeleri olumlu.")
    elif risk < -2:
        parts.append("Risk ortamı baskılı.")

    if internals > 2:
        parts.append("Piyasa iç yapısı sağlıklı, geniş katılım var.")
    elif internals < -2:
        parts.append("Piyasa iç yapısı zayıf.")

    if timing > 2:
        parts.append("Teknik zamanlama güçlü.")
    elif timing < -2:
        parts.append("Teknik göstergeler olumsuz.")

    if breadth is not None and breadth < 35:
        parts.append(f"SMA50 üzerindeki hisse oranı %{breadth:.0f} — piyasa çok dar.")

    conclusions = {
        "AGRESİF ALIM UYGUN": "Trend, makro ve sentiment uyumlu. Agresif pozisyon alınabilir.",
        "KADEMELİ / DİKKATLİ İŞLEM": "Sinyaller karışık. Kademeli giriş yapın, defansif sektörlere ağırlık verin.",
        "NÖTR / BEKLE": "Net bir yön yok. Koşullar netleşene kadar bekleyin.",
        "GİRMEYİN / KORUMACI MOD": "Negatif sinyaller baskın. Nakit ve tahvil ağırlığını artırın.",
        "RİSKLİ / NAKİTTE BEKLE": "VIX yüksek olduğu sürece tüm sinyaller geçersiz. Nakitte bekleyin ve VIX'in 20 altına gerilemesini izleyin.",
    }
    parts.append(conclusions.get(verdict, ""))

    return " ".join(parts)


def get_verdict_style(verdict):
    return VERDICT_MAP.get(verdict, VERDICT_MAP.get("BEKLE", {
        "color": "#6B7280", "bg": "#F3F4F6", "border": "#D1D5DB", "icon": "⏸️"
    }))

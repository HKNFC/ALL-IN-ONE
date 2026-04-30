from config import VERDICT_MAP, RISK_PROFILES, BIST_LAYER_WEIGHTS, USA_LAYER_WEIGHTS, SCORE_SCALE, BIST_DECISION_THRESHOLDS, USA_DECISION_THRESHOLDS


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


def normalize_score(score, max_possible):
    """Normalize a raw score to [-1, 1] range."""
    if max_possible == 0:
        return 0
    return max(min(score / max_possible, 1.0), -1.0)


def combine_weighted_layers(layer_data, layer_weights, profile, score_scale=SCORE_SCALE):
    """
    Combine normalized layer scores with weights and profile multipliers.

    layer_data: dict of {layer_key: (score, max_possible)}
    layer_weights: dict of {layer_key: weight} (should sum to 1.0)
    profile: risk profile dict
    score_scale: scale factor for final score (default 10 -> [-10, +10])

    Returns: weighted total in [-score_scale, +score_scale]
    """
    mults = profile.get("weight_multipliers", {})
    weighted_sum = 0

    for layer_key, weight in layer_weights.items():
        if layer_key not in layer_data:
            continue
        score, max_possible = layer_data[layer_key]
        norm = normalize_score(score, max_possible)

        # Apply profile multiplier if available
        mult = mults.get(layer_key, 1.0)
        # Fallback to legacy keys
        if mult == 1.0 and layer_key == "breadth":
            mult = mults.get("health", 1.0)
        if mult == 1.0 and layer_key == "technical":
            mult = mults.get("timing", 1.0)

        weighted_sum += norm * weight * mult

    return weighted_sum * score_scale


def decide_bist(macro_score, health_score, timing_score, regime, cds_value, real_rate,
                breadth_pct, bist_usd_above, risk_profile="Dengeli", cds_trend=None,
                yabanci_oran=None, yabanci_degisim=None,
                money_flow_score=None, momentum_score=None,
                macro_max=None, health_max=None, timing_max=None,
                money_flow_max=None, momentum_max=None):
    profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["Dengeli"])
    shift = profile["threshold_shift"]

    yab_kwargs = dict(yabanci_oran=yabanci_oran, yabanci_degisim=yabanci_degisim)

    # --- Override blocks (UNCHANGED) ---
    if cds_value is not None and cds_value > 500:
        verdict = "RİSKLİ / BEKLE"
        # Compute a total for the return value
        adj_macro, adj_health, adj_timing = apply_weight_multipliers(
            macro_score, health_score, timing_score, profile
        )
        total = adj_macro + adj_health + adj_timing
        explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                                regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    if regime == "crisis":
        verdict = "RİSKLİ / BEKLE"
        adj_macro, adj_health, adj_timing = apply_weight_multipliers(
            macro_score, health_score, timing_score, profile
        )
        total = adj_macro + adj_health + adj_timing
        explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                                regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    if (bist_usd_above is not None and not bist_usd_above and
            real_rate is not None and real_rate > 3 and
            breadth_pct is not None and breadth_pct < 40):
        verdict = "GİRMEYİN"
        adj_macro, adj_health, adj_timing = apply_weight_multipliers(
            macro_score, health_score, timing_score, profile
        )
        total = adj_macro + adj_health + adj_timing
        explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                                regime, cds_value, real_rate, breadth_pct, cds_trend, **yab_kwargs)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    # --- 5-layer path ---
    use_5layer = (money_flow_score is not None and momentum_score is not None and
                  macro_max is not None and macro_max > 0)

    if use_5layer:
        layer_data = {
            "macro": (macro_score, macro_max),
            "money_flow": (money_flow_score, money_flow_max),
            "breadth": (health_score, health_max),
            "technical": (timing_score, timing_max),
            "momentum": (momentum_score, momentum_max),
        }

        total = combine_weighted_layers(layer_data, BIST_LAYER_WEIGHTS, profile)

        # CDS trend global modifier
        if cds_trend == "rising":
            total *= 0.9
        elif cds_trend == "falling":
            total *= 1.1

        # Macro negative -> dampen technical + momentum
        norm_macro = normalize_score(macro_score, macro_max)
        if norm_macro < -0.3:
            # Recalculate with dampened tech/momentum
            tech_contribution = normalize_score(timing_score, timing_max) * BIST_LAYER_WEIGHTS.get("technical", 0.15) * profile.get("weight_multipliers", {}).get("timing", 1.0) * SCORE_SCALE
            mom_contribution = normalize_score(momentum_score, momentum_max) * BIST_LAYER_WEIGHTS.get("momentum", 0.10) * profile.get("weight_multipliers", {}).get("momentum", 1.0) * SCORE_SCALE
            dampen_factor = 0.6
            total -= (tech_contribution + mom_contribution) * (1 - dampen_factor)

        # Thresholds from config
        t = BIST_DECISION_THRESHOLDS
        if total >= t["uygun"] + shift and norm_macro > 0:
            verdict = "UYGUN"
        elif total >= t["kademeli"] + shift:
            if norm_macro < -0.5:
                verdict = "DİKKATLİ"
            else:
                verdict = "KADEMELİ ALIM"
        elif total >= t["dikkatli"] + shift:
            verdict = "DİKKATLİ"
        elif total > t["bekle"] + shift:
            verdict = "BEKLE"
        else:
            verdict = "GİRMEYİN"

        # Post-check: breadth weak + bullish -> downgrade
        if breadth_pct is not None and breadth_pct < 30 and verdict in ("UYGUN", "KADEMELİ ALIM"):
            verdict = "DİKKATLİ"

        # Post-check: macro very negative + timing strong -> cap
        if norm_macro < -0.5 and normalize_score(timing_score, timing_max) > 0.5:
            if verdict in ("UYGUN", "KADEMELİ ALIM"):
                verdict = "DİKKATLİ"

    else:
        # --- Legacy 3-layer path (UNCHANGED) ---
        adj_macro, adj_health, adj_timing = apply_weight_multipliers(
            macro_score, health_score, timing_score, profile
        )

        if cds_trend == "rising":
            adj_timing *= 0.7
        elif cds_trend == "falling":
            adj_timing *= 1.3

        total = adj_macro + adj_health + adj_timing

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

    # Common: explanation, allocation, stop_loss
    explanation = generate_bist_explanation(verdict, macro_score, health_score, timing_score,
                                            regime, cds_value, real_rate, breadth_pct, cds_trend,
                                            money_flow=money_flow_score, momentum=momentum_score,
                                            **yab_kwargs)
    alloc = get_allocation(verdict, profile)
    stop = get_stop_loss(verdict, profile)
    return verdict, total, explanation, alloc, stop


def decide_usa(risk_score, internals_score, timing_score, regime, vix, vix_rising,
               breadth_pct, sma200_above, risk_profile="Dengeli",
               momentum_score=None, sentiment_score=None,
               risk_max=None, internals_max=None, timing_max=None,
               momentum_max=None, sentiment_max=None):
    profile = RISK_PROFILES.get(risk_profile, RISK_PROFILES["Dengeli"])
    shift = profile["threshold_shift"]

    # --- Override blocks (UNCHANGED) ---
    if vix is not None and vix > 25:
        verdict = "RİSKLİ / NAKİTTE BEKLE"
        adj_risk, adj_internals, adj_timing = apply_weight_multipliers(
            risk_score, internals_score, timing_score, profile,
            layer1_key="macro", layer2_key="health",
        )
        total = adj_risk + adj_internals + adj_timing
        explanation = generate_usa_explanation(verdict, risk_score, internals_score, timing_score,
                                               regime, vix, breadth_pct, total)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    if (sma200_above is not None and not sma200_above and
            breadth_pct is not None and breadth_pct < 35):
        verdict = "GİRMEYİN / KORUMACI MOD"
        adj_risk, adj_internals, adj_timing = apply_weight_multipliers(
            risk_score, internals_score, timing_score, profile,
            layer1_key="macro", layer2_key="health",
        )
        total = adj_risk + adj_internals + adj_timing
        explanation = generate_usa_explanation(verdict, risk_score, internals_score, timing_score,
                                               regime, vix, breadth_pct, total)
        alloc = get_allocation(verdict, profile)
        return verdict, total, explanation, alloc, None

    # --- 5-layer path ---
    use_5layer = (momentum_score is not None and sentiment_score is not None and
                  risk_max is not None and risk_max > 0)

    if use_5layer:
        layer_data = {
            "risk": (risk_score, risk_max),
            "breadth": (internals_score, internals_max),
            "technical": (timing_score, timing_max),
            "momentum": (momentum_score, momentum_max),
            "sentiment": (sentiment_score, sentiment_max),
        }

        total = combine_weighted_layers(layer_data, USA_LAYER_WEIGHTS, profile)

        # Breadth weak -> dampen aggressive signals
        norm_breadth = normalize_score(internals_score, internals_max)
        if norm_breadth < -0.3:
            mom_contribution = normalize_score(momentum_score, momentum_max) * USA_LAYER_WEIGHTS.get("momentum", 0.15) * profile.get("weight_multipliers", {}).get("momentum", 1.0) * SCORE_SCALE
            dampen_factor = 0.6
            total -= mom_contribution * (1 - dampen_factor)

        t = USA_DECISION_THRESHOLDS
        if total >= t["agresif"] + shift:
            verdict = "AGRESİF ALIM UYGUN"
        elif total >= t["kademeli"] + shift:
            verdict = "KADEMELİ / DİKKATLİ İŞLEM"
        elif total >= t["notr"] + shift:
            verdict = "NÖTR / BEKLE"
        else:
            verdict = "GİRMEYİN / KORUMACI MOD"

        # Post-check: breadth weak + bullish -> downgrade
        if breadth_pct is not None and breadth_pct < 35 and verdict == "AGRESİF ALIM UYGUN":
            verdict = "KADEMELİ / DİKKATLİ İŞLEM"

    else:
        # --- Legacy 3-layer path (UNCHANGED) ---
        adj_risk, adj_internals, adj_timing = apply_weight_multipliers(
            risk_score, internals_score, timing_score, profile,
            layer1_key="macro", layer2_key="health",
        )
        total = adj_risk + adj_internals + adj_timing

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
                                           regime, vix, breadth_pct, total,
                                           momentum=momentum_score, sentiment=sentiment_score)
    alloc = get_allocation(verdict, profile)
    stop = get_stop_loss(verdict, profile)
    return verdict, total, explanation, alloc, stop


def generate_bist_explanation(verdict, macro, health, timing, regime, cds, real_rate, breadth,
                              cds_trend=None, yabanci_oran=None, yabanci_degisim=None,
                              money_flow=None, momentum=None):
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

    if money_flow is not None:
        if money_flow > 2:
            parts.append("Para akışı göstergeleri olumlu.")
        elif money_flow < -2:
            parts.append("Para akışı göstergeleri olumsuz.")

    if momentum is not None:
        if momentum > 1:
            parts.append("Momentum güçlü.")
        elif momentum < -1:
            parts.append("Momentum zayıf.")

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


def generate_usa_explanation(verdict, risk, internals, timing, regime, vix, breadth, total,
                             momentum=None, sentiment=None):
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

    if momentum is not None:
        if momentum > 1:
            parts.append("Momentum göstergeleri güçlü.")
        elif momentum < -1:
            parts.append("Momentum göstergeleri zayıf.")

    if sentiment is not None:
        if sentiment > 1:
            parts.append("Piyasa sentiment'i olumlu.")
        elif sentiment < -1:
            parts.append("Piyasa sentiment'i olumsuz.")

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

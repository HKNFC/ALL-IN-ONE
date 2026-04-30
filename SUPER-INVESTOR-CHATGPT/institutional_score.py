import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

STRATEGY_PROFILES = {
    "standard": {
        "label": "Standart",
        "description": "Dengeli kurumsal analiz — tüm bloklar eşit ağırlıklı.",
        "block_weights": {
            "inst_quality": 0.25,
            "inst_growth": 0.20,
            "inst_valuation": 0.15,
            "inst_momentum": 0.25,
            "inst_flow": 0.15,
        },
    },
    "quality_compounders": {
        "label": "Kalite Bileşikleri",
        "description": "Yüksek kaliteli, düzenli büyüyen, sürdürülebilir şirketler.",
        "block_weights": {
            "inst_quality": 0.35,
            "inst_growth": 0.25,
            "inst_valuation": 0.15,
            "inst_momentum": 0.15,
            "inst_flow": 0.10,
        },
    },
    "growth_leaders": {
        "label": "Büyüme Liderleri",
        "description": "Hızlı büyüyen, güçlü momentum gösteren şirketler.",
        "block_weights": {
            "inst_quality": 0.15,
            "inst_growth": 0.30,
            "inst_valuation": 0.10,
            "inst_momentum": 0.30,
            "inst_flow": 0.15,
        },
    },
    "smart_money_breakout": {
        "label": "Akıllı Para Kırılım",
        "description": "Kurumsal akış ve momentum odaklı — kırılım adayları.",
        "block_weights": {
            "inst_quality": 0.10,
            "inst_growth": 0.10,
            "inst_valuation": 0.10,
            "inst_momentum": 0.35,
            "inst_flow": 0.35,
        },
    },
    "value_confirmation": {
        "label": "Değer + Onay",
        "description": "Ucuz ama doğrulanmış — değerleme + kalite + momentum.",
        "block_weights": {
            "inst_quality": 0.25,
            "inst_growth": 0.15,
            "inst_valuation": 0.30,
            "inst_momentum": 0.20,
            "inst_flow": 0.10,
        },
    },
}

INST_QUALITY_WEIGHTS = {
    "roic": 0.35,
    "net_margin": 0.25,
    "equity_to_assets": 0.20,
    "debt_to_equity": 0.20,
}

INST_GROWTH_WEIGHTS = {
    "revenue_growth": 0.25,
    "earnings_growth": 0.30,
    "eps_cagr_3y": 0.20,
    "margin_trend": 0.25,
}

INST_VALUATION_WEIGHTS = {
    "peg": 0.45,
    "pe": 0.30,
    "pb": 0.25,
}

INST_MOMENTUM_WEIGHTS = {
    "return_3m": 0.20,
    "return_6m": 0.25,
    "return_12m": 0.25,
    "relative_return_vs_index": 0.15,
    "distance_to_52w_high": 0.15,
}

INST_FLOW_WEIGHTS = {
    "mfi": 0.30,
    "obv_slope": 0.25,
    "volume_ratio": 0.25,
    "distance_to_52w_high": 0.20,
}

BLOCK_DEFS = {
    "inst_quality": INST_QUALITY_WEIGHTS,
    "inst_growth": INST_GROWTH_WEIGHTS,
    "inst_valuation": INST_VALUATION_WEIGHTS,
    "inst_momentum": INST_MOMENTUM_WEIGHTS,
    "inst_flow": INST_FLOW_WEIGHTS,
}

SELECTION_BLOCKS = ["inst_quality", "inst_growth", "inst_valuation"]
TIMING_BLOCKS = ["inst_momentum", "inst_flow"]

INST_REVERSE_SCORED = {
    "debt_to_equity",
    "pe",
    "pb",
    "peg",
}

INST_VALUATION_POSITIVES = {"pe", "pb", "peg"}

INST_CATEGORIES = [
    (85, 100, "Elit"),
    (70, 85, "Güçlü"),
    (55, 70, "İzleme"),
    (0, 55, "Zayıf"),
]

WINSORIZE_LOWER = 0.05
WINSORIZE_UPPER = 0.95


def _collect_all_metrics() -> List[str]:
    metrics = set()
    for w in BLOCK_DEFS.values():
        metrics.update(w.keys())
    return sorted(metrics)


def _winsorize(df: pd.DataFrame, metrics: List[str]) -> pd.DataFrame:
    result = df.copy()
    for col in metrics:
        if col not in result.columns:
            continue
        series = result[col].dropna()
        if len(series) < 3:
            continue
        lo = series.quantile(WINSORIZE_LOWER)
        hi = series.quantile(WINSORIZE_UPPER)
        result[col] = result[col].clip(lower=lo, upper=hi)
    return result


def _percentile_rank(
    df: pd.DataFrame,
    metrics: List[str],
) -> pd.DataFrame:
    ranked = pd.DataFrame(index=df.index)

    for col in metrics:
        if col not in df.columns:
            ranked[col] = np.nan
            continue

        series = df[col].copy()

        if col in INST_VALUATION_POSITIVES:
            series = series.where(series > 0, np.nan)

        valid_mask = series.notna()
        n_valid = valid_mask.sum()

        if n_valid < 2:
            ranked[col] = np.where(valid_mask, 50.0, np.nan)
            continue

        dense_rank = series.rank(method="average", na_option="keep")
        pct = ((dense_rank - 1) / (n_valid - 1)) * 100

        if col in INST_REVERSE_SCORED:
            pct = pct.where(~valid_mask, 100 - pct)

        ranked[col] = pct.round(2)

    return ranked


def _adaptive_block_score(
    percentiles: pd.DataFrame,
    weights: Dict[str, float],
) -> Tuple[pd.Series, List[Dict]]:
    cols = list(weights.keys())
    wts = np.array([weights[c] for c in cols])

    scores = np.full(len(percentiles), np.nan)
    debug_rows = []

    for i in range(len(percentiles)):
        values = np.array([
            percentiles[c].iloc[i] if c in percentiles.columns else np.nan
            for c in cols
        ])

        valid = ~np.isnan(values)
        used = [cols[j] for j in range(len(cols)) if valid[j]]
        missing = [cols[j] for j in range(len(cols)) if not valid[j]]

        if not valid.any():
            debug_rows.append({"used": [], "missing": cols.copy(), "score": None})
            continue

        active_wts = wts[valid]
        active_vals = values[valid]
        total_wt = active_wts.sum()
        if total_wt == 0:
            debug_rows.append({"used": used, "missing": missing, "score": None})
            continue

        normalized_wts = active_wts / total_wt
        score = round(float(np.sum(active_vals * normalized_wts)), 2)
        scores[i] = score
        debug_rows.append({"used": used, "missing": missing, "score": score})

    return pd.Series(scores, index=percentiles.index), debug_rows


def _categorize(score: float) -> str:
    if not np.isfinite(score):
        return "N/A"
    for lower, upper, label in INST_CATEGORIES:
        if lower <= score < upper:
            return label
    if score >= 100:
        return "Elit"
    return "N/A"


def _layer_score(result: pd.DataFrame, block_names: List[str],
                 block_weights: Dict[str, float]) -> pd.Series:
    scores = np.full(len(result), np.nan)
    for i in range(len(result)):
        vals = []
        wts = []
        for bname in block_names:
            val = result[bname].iloc[i] if bname in result.columns else np.nan
            if np.isfinite(val) if isinstance(val, (int, float)) else False:
                vals.append(val)
                wts.append(block_weights.get(bname, 0))
        if not vals:
            continue
        total_wt = sum(wts)
        if total_wt == 0:
            continue
        scores[i] = round(sum(v * w for v, w in zip(vals, wts)) / total_wt, 2)
    return pd.Series(scores, index=result.index)


def append_institutional_scores(
    df: pd.DataFrame,
    profile: str = "standard",
) -> pd.DataFrame:
    result = df.copy()

    if profile not in STRATEGY_PROFILES:
        profile = "standard"
    block_weights = STRATEGY_PROFILES[profile]["block_weights"]

    all_metrics = _collect_all_metrics()
    winsorized = _winsorize(result, all_metrics)
    pct = _percentile_rank(winsorized, all_metrics)

    tickers = result["ticker"].tolist() if "ticker" in result.columns else [str(i) for i in range(len(result))]

    all_debug = {}
    for block_name, metric_weights in BLOCK_DEFS.items():
        block_score, block_debug = _adaptive_block_score(pct, metric_weights)
        result[block_name] = block_score
        all_debug[block_name] = {tickers[i]: block_debug[i] for i in range(len(block_debug))}

    result["selection_score"] = _layer_score(result, SELECTION_BLOCKS, block_weights)
    result["timing_score"] = _layer_score(result, TIMING_BLOCKS, block_weights)

    all_block_names = list(BLOCK_DEFS.keys())
    inst_scores = np.full(len(result), np.nan)
    for i in range(len(result)):
        vals = []
        wts = []
        for bname in all_block_names:
            val = result[bname].iloc[i] if bname in result.columns else np.nan
            if np.isfinite(val) if isinstance(val, (int, float)) else False:
                vals.append(val)
                wts.append(block_weights.get(bname, 0))
        if not vals:
            inst_scores[i] = 0.0
            continue
        total_wt = sum(wts)
        if total_wt == 0:
            inst_scores[i] = 0.0
            continue
        inst_scores[i] = round(sum(v * w for v, w in zip(vals, wts)) / total_wt, 2)

    result["institutional_score"] = inst_scores
    result["inst_category"] = pd.Series(inst_scores, index=result.index).apply(_categorize)

    result.attrs["_inst_debug"] = all_debug
    result.attrs["_inst_profile"] = profile

    return result


def get_debug_info(df: pd.DataFrame, ticker: str) -> Optional[Dict]:
    debug_data = df.attrs.get("_inst_debug")
    if not debug_data:
        return None

    info = {}
    for block_name, ticker_map in debug_data.items():
        if ticker in ticker_map:
            info[block_name] = ticker_map[ticker]
        else:
            info[block_name] = {"used": [], "missing": [], "score": None}

    return info if info else None


BLOCK_LABELS = {
    "inst_quality": "Kalite",
    "inst_growth": "Büyüme",
    "inst_valuation": "Değerleme",
    "inst_momentum": "Momentum",
    "inst_flow": "Akış",
}

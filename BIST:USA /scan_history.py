from __future__ import annotations
import json
import os
from datetime import datetime
import pandas as pd

HISTORY_FILE = "scan_history.json"


def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def add_scan_record(
    market: str,
    index_name: str,
    params: dict,
    results_df: pd.DataFrame,
) -> list:
    history = load_history()

    top5 = []
    if not results_df.empty:
        for _, row in results_df.head(5).iterrows():
            entry = {"symbol": row["Symbol"], "rs": row["RS Puanı"]}
            if market == "BIST":
                entry.update({
                    "mfi": row.get("MFI(14)", "-"),
                    "rsi": row.get("RSI(14)", "-"),
                    "vol": row.get("Volume/Avg", "-"),
                })
            else:
                entry.update({
                    "rsi": row.get("RSI(14)", "-"),
                    "adx": row.get("ADX(14)", "-"),
                    "mfi": row.get("MFI(14)", "-"),
                })
            top5.append(entry)

    record = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "market": market,
        "index": index_name or market,
        "params": params,
        "total_hits": len(results_df),
        "top5": top5,
    }

    history.insert(0, record)
    save_history(history)
    return history


def delete_record(record_id: str) -> list:
    history = load_history()
    history = [r for r in history if r["id"] != record_id]
    save_history(history)
    return history


def clear_all() -> list:
    save_history([])
    return []

"""
Telegram Bildirim Modülü — Super Investor
Rebalance günlerinde ve yaklaşan tarihlerde Telegram mesajı gönderir.
"""

import json
import os
import requests
import logging

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), ".telegram_config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            return json.load(open(CONFIG_PATH))
        except Exception:
            pass
    return {"bot_token": "", "chat_id": "", "enabled": False, "notify_days_before": 1}


def save_config(config: dict):
    try:
        json.dump(config, open(CONFIG_PATH, "w"), indent=2)
    except Exception as e:
        logger.error("Telegram config kaydedilemedi: %s", e)


def send_message(bot_token: str, chat_id: str, text: str):
    """Telegram mesajı gönder. Returns: (success, error_msg)"""
    if not bot_token or not chat_id:
        return False, "Bot token veya Chat ID eksik"
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return True, ""
        return False, data.get("description", "Bilinmeyen hata")
    except Exception as e:
        return False, str(e)


def build_rebalance_message(market: str, rebalance_date, days_left: int, top_picks: list = None) -> str:
    """Rebalance bildirim mesajı oluştur."""
    flag = "🇹🇷" if market == "BIST" else "🇺🇸"
    date_str = rebalance_date.strftime("%d.%m.%Y")

    if days_left <= 0:
        header = f"{flag} <b>BUGÜN REBALANCE GÜNÜ!</b>"
        sub = f"<b>{market}</b> portföyünüzü bugün yenilemeniz gerekiyor."
    elif days_left == 1:
        header = f"{flag} <b>Yarın Rebalance!</b>"
        sub = f"<b>{market}</b> rebalance tarihi <b>{date_str}</b> — yarın!"
    else:
        header = f"{flag} <b>Rebalance Yaklaşıyor</b>"
        sub = f"<b>{market}</b> rebalance tarihi <b>{date_str}</b> — <b>{days_left}</b> iş günü kaldı."

    msg = f"{header}\n{sub}"

    if top_picks:
        picks_str = ", ".join([f"<code>{p}</code>" for p in top_picks[:5]])
        msg += f"\n\n📊 Son tarama önerileri: {picks_str}"

    msg += "\n\n<i>Super Investor — Otomatik Bildirim</i>"
    return msg


def check_and_notify(force: bool = False):
    """
    Rebalance tarihlerini kontrol et, gerekiyorsa Telegram bildirimi gönder.
    force=True: koşul aranmaksızın gönder (test için)
    Returns: gönderilen mesajların listesi
    """
    config = load_config()
    if not config.get("enabled") and not force:
        return []

    bot_token = config.get("bot_token", "")
    chat_id = config.get("chat_id", "")
    notify_days = int(config.get("notify_days_before", 1))

    if not bot_token or not chat_id:
        return []

    # Bugün bildirim gönderildi mi? (tekrar göndermeyi önle)
    sent_log_path = os.path.join(os.path.dirname(__file__), ".telegram_sent_log.json")
    from datetime import date
    today_str = str(date.today())
    sent_log = {}
    if os.path.exists(sent_log_path):
        try:
            sent_log = json.load(open(sent_log_path))
        except Exception:
            pass

    # Rebalance tarihlerini yükle
    reb_save_path = os.path.join(os.path.dirname(__file__), ".last_rebalance_date.json")
    if not os.path.exists(reb_save_path):
        return []
    try:
        reb_data = json.load(open(reb_save_path))
    except Exception:
        return []

    from rebalance_utils import next_rebalance_date, trading_days_until

    sent_messages = []

    for market_key, reb_key, freq_key in [
        ("BIST", "bist_last_reb", "bist_freq"),
        ("USA",  "usa_last_reb",  "usa_freq"),
    ]:
        last_reb_str = reb_data.get(reb_key)
        if not last_reb_str:
            continue
        freq = reb_data.get(freq_key, "1m")
        last_reb = date.fromisoformat(last_reb_str)
        next_reb = next_rebalance_date(last_reb, freq=freq)
        days_left = trading_days_until(next_reb, from_date=date.today())

        should_notify = force or days_left <= notify_days
        log_key = f"{today_str}_{market_key}"

        if should_notify and (force or log_key not in sent_log):
            msg = build_rebalance_message(market_key, next_reb, days_left)
            ok, err = send_message(bot_token, chat_id, msg)
            if ok:
                sent_log[log_key] = True
                sent_messages.append(f"{market_key}: {days_left} iş günü kaldı — mesaj gönderildi")
            else:
                sent_messages.append(f"{market_key}: HATA — {err}")

    try:
        json.dump(sent_log, open(sent_log_path, "w"), indent=2)
    except Exception:
        pass

    return sent_messages

"""
Rebalance Scheduler — Super Investor
Her sabah 09:00'da (yerel saat) Telegram bildirimi kontrol eder.
Arka planda daemon thread olarak çalışır.
Kullanım: python3 rebalance_scheduler.py
"""

import time
import logging
import threading
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(message)s",
    handlers=[
        logging.FileHandler("/tmp/super_investor_scheduler.log"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def _run_check():
    try:
        from telegram_notifier import check_and_notify
        results = check_and_notify(force=False)
        if results:
            for r in results:
                logger.info("Bildirim: %s", r)
        else:
            logger.info("Bildirim gönderilmedi (koşul yok veya devre dışı)")
    except Exception as e:
        logger.error("Kontrol hatası: %s", e)


def scheduler_loop():
    logger.info("Rebalance scheduler başladı.")
    while True:
        now = datetime.now()
        # Her sabah 09:00'da çalıştır (Pazartesi-Cuma)
        if now.weekday() < 5 and now.hour == 9 and now.minute == 0:
            logger.info("Günlük kontrol çalışıyor...")
            _run_check()
            time.sleep(61)  # Aynı dakikada tekrar tetiklememek için
        else:
            time.sleep(30)  # 30 sn'de bir kontrol et


def start_background_scheduler():
    """Streamlit app.py'den çağrılır — daemon thread başlatır."""
    t = threading.Thread(target=scheduler_loop, daemon=True, name="RebalanceScheduler")
    t.start()
    logger.info("Rebalance scheduler arka planda başlatıldı.")
    return t


if __name__ == "__main__":
    # Doğrudan çalıştırma
    scheduler_loop()

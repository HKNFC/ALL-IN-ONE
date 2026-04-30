#!/usr/bin/env python3
"""
Borsa Portföy Seçici — Watchdog
Uygulama çökmüşse veya yanıt vermiyorsa otomatik yeniden başlatır.
Arka planda çalıştırılır: python3 watchdog.py &
"""
import os
import sys
import time
import subprocess
import urllib.request
from datetime import datetime

PORT       = 5556
CHECK_SEC  = 30      # kaç saniyede bir kontrol
MAX_FAILS  = 3       # kaç başarısız kontrolden sonra yeniden başlat
LOG_FILE   = os.path.join(os.path.dirname(__file__), "watchdog.log")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
APP_PATH   = os.path.join(BASE_DIR, "app.py")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_alive() -> bool:
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/_stcore/health",
            headers={"User-Agent": "watchdog/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def kill_existing():
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{PORT}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            try:
                os.kill(int(pid), 15)
            except Exception:
                pass
        if pids:
            time.sleep(2)
    except Exception:
        pass


def start_app():
    kill_existing()
    log(f"Uygulama başlatılıyor (port {PORT})...")
    env = os.environ.copy()
    env["STREAMLIT_SERVER_PORT"] = str(PORT)
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", APP_PATH,
         "--server.port", str(PORT),
         "--server.headless", "true"],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Başlaması için bekle
    for _ in range(30):
        time.sleep(2)
        if is_alive():
            log(f"Uygulama hazır (PID {proc.pid})")
            return proc
    log("UYARI: Uygulama 60 saniyede başlamadı.")
    return proc


def run():
    log("Watchdog başlatıldı.")
    proc = None
    fail_count = 0

    # İlk başlangıç
    if not is_alive():
        proc = start_app()
    else:
        log("Uygulama zaten çalışıyor.")

    while True:
        time.sleep(CHECK_SEC)
        if is_alive():
            fail_count = 0
        else:
            fail_count += 1
            log(f"Yanıt yok ({fail_count}/{MAX_FAILS})...")
            if fail_count >= MAX_FAILS:
                log("Uygulama yeniden başlatılıyor...")
                if proc:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                proc = start_app()
                fail_count = 0


if __name__ == "__main__":
    run()

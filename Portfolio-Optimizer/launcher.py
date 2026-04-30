import multiprocessing
multiprocessing.freeze_support()

import os
import sys

os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
os.environ.setdefault("STREAMLIT_SERVER_ENABLE_CORS", "false")
os.environ.setdefault("STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION", "false")
os.environ.setdefault("STREAMLIT_THEME_BASE", "dark")
os.environ.setdefault("STREAMLIT_THEME_PRIMARY_COLOR", "#00CC96")
os.environ.setdefault("STREAMLIT_THEME_BACKGROUND_COLOR", "#0E1117")
os.environ.setdefault("STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR", "#262730")

PREFERRED_PORT = 5556   # localhost:5556 ile koordineli çalış

# Worker modu: bu process sadece Streamlit sunucusunu çalıştırır
if os.environ.get("BORSA_WORKER_PORT"):
    import socket, time

    port = int(os.environ["BORSA_WORKER_PORT"])

    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    if base not in sys.path:
        sys.path.insert(0, base)

    app_path = os.path.join(base, "app.py")

    import streamlit.config as _cfg
    try:
        _cfg._on_config_parsed.disconnect(_cfg._check_conflicts)
    except Exception:
        pass
    try:
        _cfg._on_config_parsed.receivers.clear()
    except Exception:
        pass
    _cfg.set_option("global.developmentMode", False)
    _cfg.set_option("server.port", port)
    _cfg.set_option("server.headless", True)
    _cfg.set_option("server.enableCORS", False)
    _cfg.set_option("server.enableXsrfProtection", False)
    _cfg.set_option("browser.gatherUsageStats", False)

    from streamlit.web import bootstrap
    bootstrap.run(app_path, False, [], {})
    sys.exit(0)


# ── Ana launcher ──────────────────────────────────────────────────────────

import time
import socket
import tempfile
import threading
import subprocess

LOCK_FILE = os.path.join(tempfile.gettempdir(), "borsa_portfoy.lock")


def is_port_open(port, host="127.0.0.1") -> bool:
    """Verilen portta bir sunucu çalışıyor mu?"""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def find_free_port(start=8600, end=8700):
    for p in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def acquire_lock(port):
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                parts = f.read().strip().split(":")
            old_pid = int(parts[0])
            os.kill(old_pid, 0)
            sys.exit(0)
        except (ValueError, OSError):
            try:
                os.remove(LOCK_FILE)
            except OSError:
                pass
    with open(LOCK_FILE, "w") as f:
        f.write(f"{os.getpid()}:{port}")


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


def wait_for_server(port, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_open(port):
            return True
        time.sleep(0.5)
    return False


def spawn_worker(port):
    env = os.environ.copy()
    env["BORSA_WORKER_PORT"] = str(port)

    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, os.path.abspath(__file__)]

    return subprocess.Popen(
        cmd, env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


LOADING_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0E1117;display:flex;flex-direction:column;
     align-items:center;justify-content:center;height:100vh;
     font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#FAFAFA}
.icon{font-size:64px;margin-bottom:20px}
h1{font-size:24px;font-weight:700;color:#00CC96;margin-bottom:8px}
p{font-size:15px;color:#aaa;margin-bottom:36px}
.bar{width:240px;height:4px;background:#262730;border-radius:2px;overflow:hidden}
.fill{height:100%;width:35%;background:#00CC96;border-radius:2px;
      animation:s 1.4s ease-in-out infinite}
@keyframes s{0%{transform:translateX(-120%)}100%{transform:translateX(420%)}}
</style></head><body>
<div class="icon">📈</div>
<h1>Borsa Portföy Seçici</h1>
<p>Uygulama başlatılıyor...</p>
<div class="bar"><div class="fill"></div></div>
</body></html>"""

ERROR_HTML = """<body style='background:#0E1117;color:#ff4b4b;
font-family:sans-serif;padding:60px;font-size:18px'>
❌ Sunucu başlatılamadı. Uygulamayı kapatıp tekrar deneyin.</body>"""


def run_launcher():
    import webview

    # ── Önce 5556'da sunucu var mı kontrol et ────────────────────────────────
    existing_server = is_port_open(PREFERRED_PORT)

    if existing_server:
        # localhost:5556 çalışıyor → direkt bağlan, kendi sunucumuzu başlatma
        port = PREFERRED_PORT
        proc = None
        acquire_lock(port)
    else:
        # 5556 boş → kendi sunucumuzu 5556'da başlat
        port = PREFERRED_PORT
        acquire_lock(port)
        proc = spawn_worker(port)

    window = webview.create_window(
        title="Borsa Portföy Seçici",
        html=LOADING_HTML,
        width=1440,
        height=900,
        min_size=(960, 640),
        resizable=True,
        text_select=True,
    )

    def load_app():
        if existing_server:
            # Zaten çalışıyor, kısa bekle sonra yükle
            time.sleep(0.5)
            window.load_url(f"http://127.0.0.1:{port}")
        else:
            if wait_for_server(port, timeout=90):
                window.load_url(f"http://127.0.0.1:{port}")
            else:
                window.load_html(ERROR_HTML)

    def on_closed():
        # Masaüstü kapatılınca: sadece bizim başlattığımız sunucuyu durdur
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        release_lock()

    threading.Thread(target=load_app, daemon=True).start()
    window.events.closed += on_closed

    webview.start(gui="cocoa", debug=False)

    if proc is not None:
        proc.terminate()
    release_lock()


if __name__ == "__main__":
    run_launcher()

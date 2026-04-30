"""
ALL-IN-ONE INVESTING PLATFORM — Masaüstü Başlatıcı
Flask portal (5600) + tüm sub-app'leri başlatır, native pencere açar.
"""
import multiprocessing
multiprocessing.freeze_support()

import os, sys, time, socket, threading, subprocess, tempfile

PORTAL_PORT = 5600
LOCK_FILE   = os.path.join(tempfile.gettempdir(), "allinone_platform.lock")
AI_DIR      = "/Users/hakanficicilar/Documents/Aİ"
PLATFORM_DIR= os.path.dirname(os.path.abspath(__file__))
LOG_DIR     = os.path.join(PLATFORM_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def is_port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1): return True
    except: return False

def wait_for_port(port, timeout=90):
    t = time.time()
    while time.time()-t < timeout:
        if is_port_open(port): return True
        time.sleep(0.5)
    return False

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            pid = int(open(LOCK_FILE).read().strip())
            os.kill(pid, 0)
            sys.exit(0)
        except: os.remove(LOCK_FILE)
    open(LOCK_FILE,"w").write(str(os.getpid()))

def release_lock():
    try: os.remove(LOCK_FILE)
    except: pass

def log(name): return open(os.path.join(LOG_DIR,f"{name}.log"),"a")

def start_flask(cwd, port, logname):
    return subprocess.Popen(
        ["/usr/bin/python3","app.py"], cwd=cwd,
        stdout=log(logname), stderr=subprocess.STDOUT)

def start_streamlit(cwd, port, logname):
    return subprocess.Popen(
        ["/usr/bin/python3","-m","streamlit","run","app.py",
         "--server.port",str(port),"--server.headless","true",
         "--server.enableCORS","false","--server.enableXsrfProtection","false",
         "--browser.gatherUsageStats","false"],
        cwd=cwd, stdout=log(logname), stderr=subprocess.STDOUT)

def launch_all():
    procs=[]
    def go(port, fn, *args):
        if not is_port_open(port):
            try: procs.append(fn(*args))
            except Exception as e: print(f"[WARN] {port}: {e}")
    go(5555, start_flask,  os.path.join(AI_DIR,"MARK MİNERVİNİ"),          5555,"minervini")
    go(8501, start_streamlit, os.path.join(AI_DIR,"GEMINI-PIYASA-ZAMANLAMA-MODULU"), 8501,"gemini")
    go(8502, start_streamlit, os.path.join(AI_DIR,"Portfolio-Optimizer"),   8502,"borsa")
    go(8503, start_streamlit, os.path.join(AI_DIR,"SUPER-INVESTOR-CHATGPT"),8503,"super")
    go(5600, start_flask,  PLATFORM_DIR,                                    5600,"portal")
    return procs

LOADING_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0A0E1A;display:flex;flex-direction:column;align-items:center;
justify-content:center;height:100vh;font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#F0F4FF}
.logo{font-size:72px;margin-bottom:24px}
h1{font-size:26px;font-weight:700;background:linear-gradient(135deg,#00C896,#0088FF);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:6px}
.sub{font-size:13px;color:#6B7A99;margin-bottom:36px}
.mods{display:flex;flex-wrap:wrap;justify-content:center;gap:12px;margin-bottom:40px;max-width:600px}
.mod{background:#13192B;border:1px solid #1E2740;border-radius:10px;padding:10px 16px;
font-size:12px;color:#8892AA;display:flex;align-items:center;gap:8px}
.dot{width:7px;height:7px;border-radius:50%;background:#1E2740;animation:p 1.5s ease infinite}
.d1{animation-delay:0s}.d2{animation-delay:.25s}.d3{animation-delay:.5s}.d4{animation-delay:.75s}.d5{animation-delay:1s}
@keyframes p{0%,100%{background:#1E2740}50%{background:#00C896;box-shadow:0 0 6px rgba(0,200,150,.6)}}
.bar{width:260px;height:3px;background:#1E2740;border-radius:2px;overflow:hidden}
.fill{height:100%;width:28%;background:linear-gradient(90deg,#00C896,#0088FF);
border-radius:2px;animation:s 1.5s ease-in-out infinite}
@keyframes s{0%{transform:translateX(-160%)}100%{transform:translateX(520%)}}
</style></head><body>
<div class="logo">📊</div>
<h1>ALL-IN-ONE INVESTING PLATFORM</h1>
<p class="sub">Modüller başlatılıyor, lütfen bekleyin...</p>
<div class="mods">
<div class="mod"><div class="dot d1"></div>Piyasa Zamanlaması</div>
<div class="mod"><div class="dot d2"></div>Mark Minervini</div>
<div class="mod"><div class="dot d3"></div>Portföy Optimizer</div>
<div class="mod"><div class="dot d4"></div>Super Investor</div>
<div class="mod"><div class="dot d5"></div>Portal</div>
</div>
<div class="bar"><div class="fill"></div></div>
</body></html>"""

ERROR_HTML = "<body style='background:#0A0E1A;color:#FF4B4B;font-family:sans-serif;padding:80px;text-align:center;font-size:18px'><div style='font-size:48px;margin-bottom:20px'>⚠️</div><div>Portal başlatılamadı.<br>Uygulamayı kapatıp tekrar deneyin.</div></body>"

def run():
    acquire_lock()
    already = is_port_open(PORTAL_PORT)
    procs = [] if already else launch_all()

    import webview
    win = webview.create_window(
        "ALL-IN-ONE Investing Platform", html=LOADING_HTML,
        width=1600, height=960, min_size=(1200,700),
        resizable=True, text_select=True)

    def load():
        if not already and not wait_for_port(PORTAL_PORT, 90):
            win.load_html(ERROR_HTML); return
        time.sleep(0.3 if already else 0)
        win.load_url(f"http://127.0.0.1:{PORTAL_PORT}")

    def on_close():
        for p in procs:
            try: p.terminate(); p.wait(timeout=5)
            except: pass
        release_lock()

    threading.Thread(target=load, daemon=True).start()
    win.events.closed += on_close
    webview.start(gui="cocoa", debug=False)
    for p in procs:
        try: p.terminate()
        except: pass
    release_lock()

if __name__ == "__main__":
    run()

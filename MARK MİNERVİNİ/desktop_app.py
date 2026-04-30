"""
SEPA Stock Scanner - Desktop Application Entry Point
Wraps Flask backend in a native PyWebView window.
"""

import sys
import os
import threading
import time
import socket


def resource_path(relative):
    """PyInstaller paketlenmiş uygulamada doğru dosya yolunu döndürür."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def wait_for_server(host='127.0.0.1', port=5555, timeout=30):
    """Flask sunucusu hazır olana kadar bekler."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    return False


def start_flask():
    """Flask uygulamasını arka planda başlatır."""
    # PyInstaller paketi içinde doğru dizini sys.path'e ekle
    src_dir = resource_path('.')
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    # Çalışma dizinini kaynak dizinine çek (CSV, templates vs. için)
    os.chdir(src_dir)

    from app import app as flask_app
    flask_app.run(debug=False, host='127.0.0.1', port=5555, use_reloader=False)


def main():
    import webview

    # Flask'ı ayrı thread'de başlat
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Sunucu hazır olana kadar bekle
    print("⏳ Sunucu başlatılıyor...")
    if not wait_for_server():
        print("❌ Sunucu başlatılamadı!")
        sys.exit(1)
    print("✅ Sunucu hazır.")

    # Native pencere aç
    window = webview.create_window(
        title='SEPA Stock Scanner',
        url='http://127.0.0.1:5555',
        width=1440,
        height=900,
        min_size=(1024, 700),
        resizable=True,
        fullscreen=False,
    )

    webview.start(debug=False)


if __name__ == '__main__':
    main()

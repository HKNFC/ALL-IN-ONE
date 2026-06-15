import os
import sys
import time
import socket
import threading
import subprocess
import webview

PORT = 5001
URL = f"http://localhost:{PORT}"


def is_port_open(port, timeout=1.0):
    try:
        with socket.create_connection(("localhost", port), timeout=timeout):
            return True
    except OSError:
        return False


def start_streamlit():
    base = os.path.dirname(os.path.abspath(__file__))
    streamlit_bin = os.path.join(os.path.dirname(sys.executable), "streamlit")
    app_path = os.path.join(base, "app.py")
    env = os.environ.copy()
    env["TWELVE_DATA_API_KEY"] = "e7e92117f1e6465685829ea63688503f"
    subprocess.Popen(
        [streamlit_bin, "run", app_path,
         "--server.port", str(PORT),
         "--server.address", "localhost",
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=base,
    )


def wait_and_load(window):
    for _ in range(120):
        if is_port_open(PORT):
            break
        time.sleep(0.5)
    window.load_url(URL)


def main():
    if not is_port_open(PORT):
        start_streamlit()

    window = webview.create_window(
        title="Super Investor",
        url="about:blank",
        width=1600,
        height=1000,
        min_size=(1024, 700),
    )
    threading.Thread(target=wait_and_load, args=(window,), daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()

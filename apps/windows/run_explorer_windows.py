"""Resilient cross-platform launcher for AlphaFold 3 Explorer on Windows.
Runs with zero external dependencies (standard Python library only).
Guarantees immediate responsiveness: never hangs, never crashes with missing module errors,
and waits until the loopback server is ready before launching the app window.
"""
import functools
import http.server
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = 8765

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0

def ping_server(port, timeout=0.6):
    for endpoint in ('/api/status', '/'):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}{endpoint}")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 304):
                    return True
        except Exception:
            pass
    return False

def wait_for_server(port, max_wait=6.0):
    start = time.time()
    while time.time() - start < max_wait:
        if is_port_in_use(port):
            return True
        time.sleep(0.1)
    return False

def open_window(url, port=PORT):
    # Ensure server is ready before popping window so user never sees connection refused
    wait_for_server(port)
    time.sleep(0.3)

    if sys.platform == "win32":
        # Windows 10 & 11 include Microsoft Edge by default.
        edge_candidates = [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for ep in edge_candidates:
            if os.path.isfile(ep):
                try:
                    subprocess.Popen([ep, f"--app={url}", "--window-size=1360,900"])
                    return
                except Exception:
                    pass

        # Try Google Chrome as fallback
        chrome_candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
        for cp in chrome_candidates:
            if os.path.isfile(cp):
                try:
                    subprocess.Popen([cp, f"--app={url}", "--window-size=1360,900"])
                    return
                except Exception:
                    pass

    # Standard browser fallback
    try:
        webbrowser.open(url)
    except Exception:
        pass

def try_import_af3():
    """Look for the full local AlphaFold 3 backend."""
    candidates = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        os.path.expanduser("~/alphafold3"),
        os.getcwd(),
    ]
    for c in candidates:
        if os.path.isdir(c) and os.path.isfile(os.path.join(c, "explorer", "app.py")):
            if c not in sys.path:
                sys.path.insert(0, c)
            try:
                from explorer.app import main as app_main
                return app_main
            except Exception as e:
                print(f"[Notice] AF3 backend in {c} not ready yet ({e}). Using embedded studio.")
    return None

def run_embedded_server(web_dir, start_port=PORT):
    """Serve embedded offline studio with zero dependencies and port collision protection."""
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def end_headers(self):
            self.send_header('Cache-Control', 'no-cache')
            super().end_headers()

    handler = functools.partial(QuietHandler, directory=web_dir)
    socketserver.TCPServer.allow_reuse_address = True

    httpd = None
    port = start_port
    for candidate in range(start_port, start_port + 25):
        try:
            httpd = socketserver.TCPServer(('127.0.0.1', candidate), handler)
            port = candidate
            break
        except OSError:
            continue

    if httpd is None:
        raise RuntimeError("Could not find an available local port for the embedded server.")

    app_url = f"http://127.0.0.1:{port}/?mode=explorer"
    print(f"[OK] Embedded studio running at {app_url}")

    # Launch browser after server is listening
    threading.Thread(target=open_window, args=(app_url, port), daemon=True).start()

    with httpd:
        httpd.serve_forever()

def main():
    print("=" * 68)
    print("        AlphaFold 3 Explorer - Desktop Studio for Windows")
    print("=" * 68)

    port = PORT

    # If backend or studio is already running, open directly
    if ping_server(port):
        print(f"[OK] Connected to running server at http://127.0.0.1:{port}")
        open_window(f"http://127.0.0.1:{port}/?mode=explorer", port)
        return

    # Check for full local backend
    af3_app_main = try_import_af3()

    if af3_app_main is not None:
        print("[1/2] Starting full local AlphaFold 3 backend...")
        threading.Thread(target=open_window, args=(f"http://127.0.0.1:{port}/?mode=explorer", port), daemon=True).start()
        try:
            af3_app_main()
            return
        except Exception as err:
            print(f"[Notice] Backend startup failed ({err}). Falling back to embedded studio.")

    # Fallback to embedded self-contained web studio
    web_dir = os.path.join(os.path.dirname(__file__), "web")
    if not os.path.isdir(web_dir):
        # Fallback to current directory or explorer/static
        web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "explorer", "static"))

    print(f"[1/2] Starting local desktop studio...")
    print(f"[2/2] Opening application window...")
    print("\nAlphaFold 3 Explorer is active! Press Ctrl+C to close.")

    try:
        run_embedded_server(web_dir, port)
    except KeyboardInterrupt:
        print("\nAlphaFold 3 Explorer closed.")

if __name__ == "__main__":
    main()

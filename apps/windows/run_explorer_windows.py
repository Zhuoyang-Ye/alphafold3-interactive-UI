"""Cross-platform Python launcher for AlphaFold 3 Explorer on Windows."""
import os
import sys
import subprocess
import time
import webbrowser

def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    os.chdir(root)
    port = 8765
    url = f"http://127.0.0.1:{port}"

    print("=" * 65)
    print("        AlphaFold 3 Explorer - Desktop Studio")
    print("=" * 65)
    print(f"Working directory: {root}")
    print(f"Starting server on {url} ...\n")

    # Try launching Edge in app mode on Windows
    def open_browser():
        time.sleep(1.5)
        if sys.platform == "win32":
            edge_paths = [
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            ]
            for ep in edge_paths:
                if os.path.exists(ep):
                    subprocess.Popen([ep, f"--app={url}", "--window-size=1360,900"])
                    return
        webbrowser.open(url)

    import threading
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()

    from explorer.app import main as app_main
    app_main()

if __name__ == "__main__":
    main()

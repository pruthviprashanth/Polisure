"""Start PoliSure locally: API on :8000 + web on :3000, open the browser, Ctrl+C stops both.

    python run.py            real backend (backend/, uvicorn app.main:app)
    python run.py --mock     mock API (mock/server.py), no keys, no LLM calls
    python run.py --no-browser

Works on Windows (PowerShell) and macOS/Linux.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
API_PORT = 8000
WEB_PORT = 3000
IS_WIN = os.name == "nt"


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for(port: int, timeout: float, procs: list[subprocess.Popen]) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if port_open(port):
            return True
        if any(p.poll() is not None for p in procs):
            return False
        time.sleep(0.5)
    return False


def spawn(cmd: list[str], cwd: Path, env: dict) -> subprocess.Popen:
    kw: dict = {"cwd": str(cwd), "env": env}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(cmd, **kw)


def stop(p: subprocess.Popen) -> None:
    if p.poll() is not None:
        return
    try:
        if IS_WIN:
            # npm.cmd starts node as a child; /T kills the whole tree.
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        p.wait(timeout=10)
    except Exception:
        p.kill()


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # show progress promptly even when output is piped
    # Treat Ctrl+Break (Windows) and SIGTERM like Ctrl+C so both children are always stopped.
    for name in ("SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mock", action="store_true", help="use mock/server.py instead of the real backend")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser")
    args = ap.parse_args()

    npm = shutil.which("npm")  # resolves npm.cmd on Windows
    if not npm:
        print("npm was not found on PATH. Install Node.js 20+ from https://nodejs.org and try again.")
        return 1
    for port in (API_PORT, WEB_PORT):
        if port_open(port):
            print(f"Port {port} is already in use. Stop whatever is running there (or an earlier run.py) first.")
            return 1

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    if args.mock:
        api_cmd, api_cwd, label = [sys.executable, str(ROOT / "mock" / "server.py")], ROOT, "mock API"
    else:
        if not (ROOT / "backend" / "app" / "main.py").exists():
            print("backend/app/main.py not found. Use `python run.py --mock` to run against the mock server.")
            return 1
        api_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(API_PORT)]
        api_cwd, label = ROOT / "backend", "backend API"

    if not (WEB / "node_modules").exists():
        print("Installing web dependencies (first run only)...")
        if subprocess.run([npm, "install"], cwd=str(WEB)).returncode != 0:
            print("npm install failed.")
            return 1

    web_env = {**env, "NEXT_PUBLIC_API_URL": f"http://localhost:{API_PORT}", "PORT": str(WEB_PORT)}
    procs: list[subprocess.Popen] = []
    try:
        print(f"Starting {label} on http://localhost:{API_PORT} ...")
        procs.append(spawn(api_cmd, api_cwd, env))
        if not wait_for(API_PORT, 60, procs):
            print(f"The {label} did not start. See the messages above (missing venv packages? run `pip install -r requirements.txt`).")
            return 1
        print(f"Starting web on http://localhost:{WEB_PORT} ...")
        procs.append(spawn([npm, "run", "dev", "--", "--port", str(WEB_PORT)], WEB, web_env))
        if not wait_for(WEB_PORT, 120, procs):
            print("The web app did not start. See the messages above.")
            return 1
        url = f"http://localhost:{WEB_PORT}"
        print(f"\nPoliSure is running{' (MOCK API)' if args.mock else ''}: {url}\nPress Ctrl+C to stop.\n")
        if not args.no_browser:
            webbrowser.open(url)
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("One of the processes exited; stopping the other.")
        return 1
    except KeyboardInterrupt:
        print("\nStopping...")
        return 0
    finally:
        for p in reversed(procs):
            stop(p)


if __name__ == "__main__":
    sys.exit(main())

"""Install Eyrie as a macOS launchd agent (runs in the background, starts at login).

    python3 scripts/launchd.py install [--port 8787] [--dry-run]
    python3 scripts/launchd.py uninstall [--dry-run]
    python3 scripts/launchd.py status

Stdlib only. The agent runs the backend from this checkout and serves the built UI, on
127.0.0.1 only. Re-run install after pulling changes; it rewrites the agent and restarts it.
"""
import argparse
import os
import plistlib
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LABEL = "local.eyrie"
REPO = Path(__file__).resolve().parents[1]
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / ".eyrie/logs/eyrie.log"
DOMAIN = f"gui/{os.getuid()}"


def agent(port: int, path_env: str) -> dict:
    backend = REPO / "backend"
    return {
        "Label": LABEL,
        "ProgramArguments": [str(backend / ".venv/bin/uvicorn"), "app.main:create_app", "--factory",
                             "--host", "127.0.0.1", "--port", str(port)],
        "WorkingDirectory": str(backend),
        # launchd's default PATH is /usr/bin:/bin:/usr/sbin:/sbin; claude, codex and tmux usually
        # live elsewhere (~/.local/bin, /opt/homebrew/bin), so keep the PATH install ran with.
        "EnvironmentVariables": {"PATH": path_env},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        # Sessions are tmux processes Eyrie started; restarting or unloading Eyrie must not kill them.
        "AbandonProcessGroup": True,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }


def run(cmd: list[str], dry: bool, check: bool = True) -> int:
    print("$ " + " ".join(cmd))
    if dry:
        return 0
    return subprocess.run(cmd, check=check).returncode


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def loaded() -> bool:
    return subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True).returncode == 0


def install(port: int, dry: bool) -> None:
    if not (REPO / "backend/.venv/bin/uvicorn").exists():
        sys.exit("backend/.venv isn't set up; run `make setup` first")
    if not (REPO / "frontend/dist/index.html").exists():
        sys.exit("UI isn't built; run `make build` first")
    data = plistlib.dumps(agent(port, os.environ.get("PATH", "/usr/bin:/bin")))
    print(f"# {PLIST}")
    if dry:
        print(data.decode())
    else:
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        tmp = PLIST.with_suffix(".plist.tmp")
        tmp.write_bytes(data)
        subprocess.run(["plutil", "-lint", str(tmp)], check=True, capture_output=True)
        tmp.replace(PLIST)
    if dry or loaded():
        run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], dry, check=False)
        if not dry:
            for _ in range(50):  # bootout returns before the job is fully gone
                if not loaded():
                    break
                time.sleep(0.1)
    run(["launchctl", "bootstrap", DOMAIN, str(PLIST)], dry)
    if dry:
        return
    for _ in range(50):
        if healthy(port):
            print(f"Eyrie is running: http://127.0.0.1:{port}  (logs: {LOG})")
            return
        time.sleep(0.2)
    sys.exit(f"Eyrie didn't answer on port {port} within 10s; check {LOG}")


def uninstall(dry: bool) -> None:
    if dry or loaded():
        run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], dry, check=False)
    if dry or PLIST.exists():
        print(f"$ rm {PLIST}")
        if not dry:
            PLIST.unlink()
    print("Eyrie's background agent is removed. Running tmux sessions were left alone (tmux -L eyrie ls).")


def status() -> None:
    if not PLIST.exists():
        print("Not installed (run `make install`).")
        return
    port = int(plistlib.loads(PLIST.read_bytes())["ProgramArguments"][-1])
    state = "loaded" if loaded() else "installed but not loaded"
    print(f"{LABEL}: {state}; http://127.0.0.1:{port} {'answers' if healthy(port) else 'is not answering'}")
    print(f"logs: {LOG}")


def main() -> None:
    if sys.platform != "darwin":
        sys.exit("launchd install is macOS-only; run `make serve` instead")
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["install", "uninstall", "status"])
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    {"install": lambda: install(a.port, a.dry_run), "uninstall": lambda: uninstall(a.dry_run), "status": status}[a.command]()


if __name__ == "__main__":
    main()

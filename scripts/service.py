"""Run Eyrie in the background as a per-user service: a launchd agent on macOS, a systemd
user unit on Linux (Ubuntu). Stdlib only.

    python3 scripts/service.py install [--port 8787] [--dry-run]
    python3 scripts/service.py uninstall [--dry-run]
    python3 scripts/service.py status

The service runs the backend from this checkout and serves the built UI on 127.0.0.1 only.
Re-run install after pulling changes: it rewrites the service and restarts it. Uninstalling
never touches running tmux sessions or ~/.eyrie.
"""
import argparse
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
LOG = Path.home() / ".eyrie/logs/eyrie.log"
TOOLS = ("claude", "codex", "tmux")
MARK = re.compile(r"__EYRIE_PATH__(.*?)__END__", re.S)


def login_path() -> str:
    """The PATH your login shell sets up, starting from a clean environment, so the service
    finds claude/codex/tmux the way your terminal does, wherever install is run from.
    (Services don't see your shell's PATH: launchd and systemd user units start minimal.)"""
    shell = os.environ.get("SHELL") or "/bin/sh"
    env = {k: os.environ[k] for k in ("HOME", "USER", "LOGNAME", "SHELL") if k in os.environ}
    env["TERM"] = "xterm-256color"
    try:
        out = subprocess.run([shell, "-lic", 'printf "__EYRIE_PATH__%s__END__" "$PATH"'], env=env,
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    m = MARK.search(out)
    if m and m.group(1).strip():
        return m.group(1).strip()
    print(f"note: couldn't read your login shell's PATH ({shell}); using the current one")
    return os.environ.get("PATH", "/usr/bin:/bin")


def uvicorn_args(port: int) -> list[str]:
    return [str(BACKEND / ".venv/bin/uvicorn"), "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port)]


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def run(cmd: list[str], dry: bool, check: bool = True) -> int:
    print("$ " + " ".join(cmd))
    return 0 if dry else subprocess.run(cmd, check=check).returncode


def write(path: Path, data: bytes, dry: bool) -> None:
    print(f"# {path}")
    if dry:
        print(data.decode())
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


# ---------------------------------------------------------------- macOS: launchd agent

class Launchd:
    label = "local.eyrie"
    path = Path.home() / "Library/LaunchAgents/local.eyrie.plist"
    domain = f"gui/{os.getuid()}"

    def render(self, port: int, path_env: str) -> bytes:
        return plistlib.dumps({
            "Label": self.label,
            "ProgramArguments": uvicorn_args(port),
            "WorkingDirectory": str(BACKEND),
            "EnvironmentVariables": {"PATH": path_env},
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            # Sessions are tmux processes Eyrie started; restarting or unloading Eyrie must not kill them.
            "AbandonProcessGroup": True,
            "StandardOutPath": str(LOG),
            "StandardErrorPath": str(LOG),
        })

    def loaded(self) -> bool:
        return subprocess.run(["launchctl", "print", f"{self.domain}/{self.label}"], capture_output=True).returncode == 0

    def install(self, port: int, path_env: str, dry: bool) -> None:
        data = self.render(port, path_env)
        write(self.path, data, dry)
        if not dry:
            subprocess.run(["plutil", "-lint", str(self.path)], check=True, capture_output=True)
        if dry or self.loaded():
            run(["launchctl", "bootout", f"{self.domain}/{self.label}"], dry, check=False)
            for _ in range(0 if dry else 50):  # bootout returns before the job is fully gone
                if not self.loaded():
                    break
                time.sleep(0.1)
        run(["launchctl", "bootstrap", self.domain, str(self.path)], dry)

    def uninstall(self, dry: bool) -> None:
        if dry or self.loaded():
            run(["launchctl", "bootout", f"{self.domain}/{self.label}"], dry, check=False)
        if dry or self.path.exists():
            print(f"$ rm {self.path}")
            if not dry:
                self.path.unlink()

    def port(self) -> int | None:
        if not self.path.exists():
            return None
        return int(plistlib.loads(self.path.read_bytes())["ProgramArguments"][-1])

    def state(self) -> str:
        return "loaded" if self.loaded() else "installed but not loaded"


# ---------------------------------------------------------------- Linux: systemd user unit

def _quote(arg: str) -> str:
    """systemd command-line quoting: spaces need double quotes; quotes and backslashes escaped."""
    if re.fullmatch(r"[\w@%+=:,./-]+", arg):
        return arg
    return '"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Systemd:
    unit = "eyrie.service"
    path = Path.home() / ".config/systemd/user/eyrie.service"

    def render(self, port: int, path_env: str) -> bytes:
        return f"""# Written by Eyrie's `make install` (scripts/service.py). Re-run it to update.
[Unit]
Description=Eyrie, local control plane for Claude Code and Codex
After=network.target

[Service]
Type=simple
WorkingDirectory={_quote(str(BACKEND))}
ExecStart={" ".join(_quote(a) for a in uvicorn_args(port))}
Environment={_quote("PATH=" + path_env)}
Restart=on-failure
RestartSec=5
# Only stop Eyrie itself: the tmux sessions it started must keep running across restarts.
KillMode=process
StandardOutput=append:{LOG}
StandardError=append:{LOG}

[Install]
WantedBy=default.target
""".encode()

    def systemctl(self, *args: str, dry: bool, check: bool = True) -> int:
        return run(["systemctl", "--user", *args], dry, check)

    def active(self) -> bool:
        return subprocess.run(["systemctl", "--user", "is-active", "--quiet", self.unit]).returncode == 0

    def install(self, port: int, path_env: str, dry: bool) -> None:
        if not dry:
            LOG.parent.mkdir(parents=True, exist_ok=True)
        write(self.path, self.render(port, path_env), dry)
        self.systemctl("daemon-reload", dry=dry)
        self.systemctl("enable", self.unit, dry=dry)
        self.systemctl("restart", self.unit, dry=dry)

    def uninstall(self, dry: bool) -> None:
        self.systemctl("disable", "--now", self.unit, dry=dry, check=False)
        if dry or self.path.exists():
            print(f"$ rm {self.path}")
            if not dry:
                self.path.unlink()
        self.systemctl("daemon-reload", dry=dry, check=False)

    def port(self) -> int | None:
        if not self.path.exists():
            return None
        m = re.search(r"--port (\d+)", self.path.read_text())
        return int(m.group(1)) if m else None

    def state(self) -> str:
        return "active" if self.active() else "installed but not running"


def backend():
    if sys.platform == "darwin":
        return Launchd()
    if sys.platform.startswith("linux"):
        if not shutil.which("systemctl"):
            sys.exit("systemd isn't available here; run `make serve` instead")
        return Systemd()
    sys.exit(f"No background service support for {sys.platform}; run `make serve` instead")


def install(port: int, dry: bool) -> None:
    if not (BACKEND / ".venv/bin/uvicorn").exists():
        sys.exit("backend/.venv isn't set up; run `make setup` first")
    if not (REPO / "frontend/dist/index.html").exists():
        sys.exit("UI isn't built; run `make build` first")
    path_env = login_path()
    missing = [t for t in TOOLS if not shutil.which(t, path=path_env)]
    if missing:
        print(f"note: not on your login PATH: {', '.join(missing)}. Eyrie will show them as missing.")
    svc = backend()
    svc.install(port, path_env, dry)
    if dry:
        return
    for _ in range(50):
        if healthy(port):
            print(f"Eyrie is running: http://127.0.0.1:{port}  (logs: {LOG})")
            if isinstance(svc, Systemd):
                print("Tip: `loginctl enable-linger` keeps it running while you're logged out.")
            return
        time.sleep(0.2)
    sys.exit(f"Eyrie didn't answer on port {port} within 10s; check {LOG}")


def uninstall(dry: bool) -> None:
    backend().uninstall(dry)
    print("Eyrie's background service is removed. Running tmux sessions were left alone (tmux -L eyrie ls).")


def status() -> None:
    svc = backend()
    port = svc.port()
    if port is None:
        print("Not installed (run `make install`).")
        return
    print(f"{type(svc).__name__.lower()}: {svc.state()}; http://127.0.0.1:{port} "
          f"{'answers' if healthy(port) else 'is not answering'}")
    print(f"logs: {LOG}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["install", "uninstall", "status"])
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    {"install": lambda: install(a.port, a.dry_run), "uninstall": lambda: uninstall(a.dry_run), "status": status}[a.command]()


if __name__ == "__main__":
    main()

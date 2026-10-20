"""Run Eyrie in the background as a per-user service: a launchd agent on macOS, a systemd
user unit on Linux.

    eyrie-server service install [--port 8787] [--ui-dir DIR] [--dry-run]
    eyrie-server service uninstall [--dry-run]
    eyrie-server service status

From a checkout it's `python -m app.cli service ...`, which is what `make install` runs.
The service runs `<program> serve --port N`: the packaged eyrie-server binary, or this
checkout's venv Python with `-m app.cli`; `serve` always binds 127.0.0.1. Re-run install
after upgrading or pulling: it rewrites the service and restarts it. Uninstalling never
touches running tmux sessions or ~/.eyrie.
"""
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Frozen: the PyInstaller binary (sys.executable is eyrie-server). Otherwise: a checkout.
FROZEN = getattr(sys, "frozen", False)
BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
LOG = Path.home() / ".eyrie/logs/eyrie.log"
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


def program() -> list[str]:
    """How to start Eyrie: the packaged binary, or this checkout's venv."""
    if FROZEN:
        return [sys.executable]
    return [str(BACKEND / ".venv/bin/python"), "-m", "app.cli"]


def serve_args(port: int) -> list[str]:
    return [*program(), "serve", "--port", str(port)]


def working_dir() -> Path:
    return Path(sys.executable).parent if FROZEN else BACKEND


def service_env(path_env: str, ui_dir: Path | None) -> dict[str, str]:
    env = {"PATH": path_env}
    if ui_dir:
        env["EYRIE_SERVER__UI_DIR"] = str(ui_dir)
    return env


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

    def render(self, port: int, path_env: str, ui_dir: Path | None = None) -> bytes:
        return plistlib.dumps({
            "Label": self.label,
            "ProgramArguments": serve_args(port),
            "WorkingDirectory": str(working_dir()),
            "EnvironmentVariables": service_env(path_env, ui_dir),
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

    def install(self, port: int, path_env: str, ui_dir: Path | None, dry: bool) -> None:
        data = self.render(port, path_env, ui_dir)
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

    def render(self, port: int, path_env: str, ui_dir: Path | None = None) -> bytes:
        env = "\n".join(f"Environment={_quote(f'{k}={v}')}" for k, v in service_env(path_env, ui_dir).items())
        return f"""# Written by `eyrie-server service install` (or `make install`). Re-run it to update.
[Unit]
Description=Eyrie, local control plane for AI coding tools
After=network.target

[Service]
Type=simple
WorkingDirectory={_quote(str(working_dir()))}
ExecStart={" ".join(_quote(a) for a in serve_args(port))}
{env}
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

    def install(self, port: int, path_env: str, ui_dir: Path | None, dry: bool) -> None:
        if not dry:
            LOG.parent.mkdir(parents=True, exist_ok=True)
        write(self.path, self.render(port, path_env, ui_dir), dry)
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
            sys.exit("systemd isn't available here; run `eyrie-server serve` yourself instead")
        return Systemd()
    sys.exit(f"No background service support for {sys.platform}; run `eyrie-server serve` instead")


def install(port: int, dry: bool, ui_dir: Path | None = None) -> None:
    if not FROZEN and not (BACKEND / ".venv/bin/python").exists():
        sys.exit("backend/.venv isn't set up; run `make setup` first")
    ui = ui_dir or (None if FROZEN else REPO / "frontend/dist")
    if not ui or not (ui / "index.html").exists():
        sys.exit(f"UI isn't built at {ui}; run `make build` first" if not FROZEN
                 else "Pass --ui-dir: the packaged UI's folder")
    from app.tools import TOOLS

    path_env = login_path()
    # tmux is required; the AI tools are whichever you use (first-run setup sorts that out).
    if not shutil.which("tmux", path=path_env):
        print("note: tmux isn't on your login PATH; Eyrie sessions need it.")
    found = [t.title for t in TOOLS.values() if shutil.which(t.binary, path=path_env)]
    print(f"Found on your login PATH: {', '.join(found) or 'no AI coding tools yet'}")
    svc = backend()
    svc.install(port, path_env, ui_dir if FROZEN or ui_dir else None, dry)
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
        print("Not installed (run `eyrie-server service install`, or `make install` from a checkout).")
        return
    print(f"{type(svc).__name__.lower()}: {svc.state()}; http://127.0.0.1:{port} "
          f"{'answers' if healthy(port) else 'is not answering'}")
    print(f"logs: {LOG}")

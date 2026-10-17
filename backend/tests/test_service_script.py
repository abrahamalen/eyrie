"""scripts/service.py: the launchd agent and systemd unit Eyrie installs (rendering only;
nothing here touches launchctl or systemctl)."""
import importlib.util
import plistlib
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("eyrie_service", Path(__file__).resolve().parents[2] / "scripts/service.py")
svc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(svc)


def test_launchd_agent():
    d = plistlib.loads(svc.Launchd().render(8787, "/opt/homebrew/bin:/usr/bin"))
    assert d["Label"] == "local.eyrie"
    assert d["ProgramArguments"][-4:] == ["--host", "127.0.0.1", "--port", "8787"]
    assert d["AbandonProcessGroup"] is True and d["KeepAlive"] is True
    assert d["EnvironmentVariables"]["PATH"] == "/opt/homebrew/bin:/usr/bin"


def test_systemd_unit_keeps_sessions_and_binds_loopback():
    unit = svc.Systemd().render(8787, "/home/me/.local/bin:/usr/bin").decode()
    assert "KillMode=process" in unit
    assert "--host 127.0.0.1 --port 8787" in unit
    assert "Environment=PATH=/home/me/.local/bin:/usr/bin" in unit
    assert "WantedBy=default.target" in unit and "Restart=on-failure" in unit


def test_systemd_quotes_paths_with_spaces(monkeypatch):
    monkeypatch.setattr(svc, "BACKEND", Path("/home/me/My Projects/eyrie/backend"))
    unit = svc.Systemd().render(8787, '/a b:/c"d').decode()
    assert 'WorkingDirectory="/home/me/My Projects/eyrie/backend"' in unit
    assert 'ExecStart="/home/me/My Projects/eyrie/backend/.venv/bin/uvicorn" app.main:create_app' in unit
    assert 'Environment="PATH=/a b:/c\\"d"' in unit


def test_port_read_back(tmp_path, monkeypatch):
    s = svc.Systemd()
    monkeypatch.setattr(svc.Systemd, "path", tmp_path / "eyrie.service")
    s.path.write_bytes(s.render(9123, "/usr/bin"))
    assert s.port() == 9123


def test_login_path_ignores_shell_noise_and_inherited_path(monkeypatch):
    seen = {}

    def fake_run(cmd, env, **kw):
        seen["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="motd\x1b[0m junk __EYRIE_PATH__/opt/x/bin:/usr/bin__END__ prompt$ ", stderr="")

    monkeypatch.setenv("PATH", "/claude/session/plugin/bin:/usr/bin")
    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    assert svc.login_path() == "/opt/x/bin:/usr/bin"
    assert "PATH" not in seen["env"]  # a clean login shell, not this process's PATH


def test_login_path_falls_back(monkeypatch):
    monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="boom"))
    monkeypatch.setenv("PATH", "/fallback/bin")
    assert svc.login_path() == "/fallback/bin"


@pytest.mark.parametrize("platform,cls", [("darwin", "Launchd"), ("linux", "Systemd")])
def test_backend_per_platform(monkeypatch, platform, cls):
    monkeypatch.setattr(svc.sys, "platform", platform)
    monkeypatch.setattr(svc.shutil, "which", lambda name, path=None: "/bin/" + name)
    assert type(svc.backend()).__name__ == cls

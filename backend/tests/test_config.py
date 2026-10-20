from pathlib import Path

import pytest

from app import config
from app.config import Settings


def test_no_personal_defaults():
    s = Settings()
    assert s.paths.tasks is None and s.tools.enabled == "auto"


def test_toml_file(monkeypatch, tmp_path):
    cfg = tmp_path / "eyrie.toml"
    cfg.write_text('[paths]\ntasks = "~/notes/todo.md"\n\n[tools]\nenabled = ["gemini"]\n\n[privacy]\nhide_mcp = ["a"]\n')
    monkeypatch.setenv("EYRIE_CONFIG", str(cfg))
    s = Settings()
    assert s.paths.tasks == Path("~/notes/todo.md").expanduser()
    assert s.tools.enabled == ["gemini"] and s.privacy.hide_mcp == ["a"]


def test_env_overrides_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "eyrie.toml"
    cfg.write_text('[sources]\nenabled = ["claude"]\n')
    monkeypatch.setenv("EYRIE_CONFIG", str(cfg))
    monkeypatch.setenv("EYRIE_SOURCES__ENABLED", '["codex"]')
    assert Settings().sources.enabled == ["codex"]


def test_user_config_wins_over_repo_config(monkeypatch, tmp_path):
    monkeypatch.delenv("EYRIE_CONFIG")
    user = tmp_path / "home/.eyrie/eyrie.toml"
    monkeypatch.setattr(config, "USER_CONFIG", user)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "repo")
    assert config.active_config() == tmp_path / "repo/eyrie.toml"  # dev checkout, no setup yet
    user.parent.mkdir(parents=True)
    user.write_text("")
    assert config.active_config() == user


def test_tools_enabled_rejects_other_strings():
    with pytest.raises(ValueError):
        config.Tools(enabled="all")

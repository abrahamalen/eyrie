from pathlib import Path

from app.config import Settings


def test_defaults_point_at_personal_tasks():
    s = Settings()
    assert s.paths.tasks_file == Path("Personal/Tasks.md")
    assert s.paths.vault.is_absolute()


def test_toml_file(monkeypatch, tmp_path):
    cfg = tmp_path / "eyrie.toml"
    cfg.write_text('[paths]\nvault = "~/notes"\n\n[privacy]\nhide_mcp = ["a"]\n')
    monkeypatch.setenv("EYRIE_CONFIG", str(cfg))
    s = Settings()
    assert s.paths.vault == Path("~/notes").expanduser()
    assert s.privacy.hide_mcp == ["a"]


def test_env_overrides_toml(monkeypatch, tmp_path):
    cfg = tmp_path / "eyrie.toml"
    cfg.write_text('[sources]\nenabled = ["claude"]\n')
    monkeypatch.setenv("EYRIE_CONFIG", str(cfg))
    monkeypatch.setenv("EYRIE_SOURCES__ENABLED", '["codex"]')
    assert Settings().sources.enabled == ["codex"]

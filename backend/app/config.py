"""Settings from eyrie.toml, overridable with EYRIE_* env vars, e.g. EYRIE_PATHS__TASKS=~/todo.md.

The file is $EYRIE_CONFIG, else ~/.eyrie/eyrie.toml (written by first-run setup and the
Settings page), else <repo>/eyrie.toml (a dev checkout's own config)."""
import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from app.usage.prices import ModelPrice

REPO_ROOT = Path(__file__).resolve().parents[2]


USER_CONFIG = Path("~/.eyrie/eyrie.toml")


def config_path() -> Path:
    """Where setup writes the config."""
    return Path(os.environ.get("EYRIE_CONFIG", USER_CONFIG)).expanduser()


def active_config() -> Path:
    """Where config is read from: the setup-written file, or a dev checkout's own."""
    p = config_path()
    if "EYRIE_CONFIG" in os.environ or p.exists():
        return p
    return REPO_ROOT / "eyrie.toml"


class Paths(BaseModel):
    model_config = ConfigDict(validate_default=True)

    claude_home: Path = Path("~/.claude")
    claude_json: Path = Path("~/.claude.json")
    codex_home: Path = Path("~/.codex")
    # Gemini CLI's ~/.gemini; with GEMINI_CLI_HOME=<dir> it lives in <dir>/.gemini.
    gemini_home: Path = Path("~/.gemini")
    # A markdown checklist for the Tasks page (e.g. a file in an Obsidian vault). Off until set.
    tasks: Path | None = None
    # Claude Code subagents' persistent memory (<agent>/*.md). Default: <claude_home>/agent-memory.
    agent_memory: Path | None = None
    data_dir: Path = Path("~/.eyrie")

    @field_validator("*")
    @classmethod
    def _expand(cls, v: Path | None) -> Path | None:
        return v.expanduser() if v is not None else None

    @property
    def memory(self) -> Path:
        return self.agent_memory or self.claude_home / "agent-memory"


class Tools(BaseModel):
    # "auto": every tool that's installed or whose state folder exists; or a list of tool ids.
    enabled: str | list[str] = "auto"

    @field_validator("enabled")
    @classmethod
    def _auto_or_list(cls, v):
        if isinstance(v, str) and v != "auto":
            raise ValueError('tools.enabled is "auto" or a list of tool ids')
        return v


class Sources(BaseModel):
    enabled: list[str] = ["sessions", "claude", "codex", "mcp", "plugins", "memory", "tasks", "usage"]


class Privacy(BaseModel):
    hide_mcp: list[str] = []


class Sessions(BaseModel):
    # Sessions may start in any directory under these roots, or in a directory Claude Code
    # or Codex has already been used in.
    roots: list[Path] = []
    # Eyrie's own tmux server, kept apart from your personal tmux sessions.
    socket: str = "eyrie"
    # A live session that has printed nothing for this long is flagged as probably waiting for you.
    idle_minutes: int = 10

    @field_validator("roots")
    @classmethod
    def _expand(cls, v: list[Path]) -> list[Path]:
        return [p.expanduser() for p in v]


class Server(BaseModel):
    # Built UI to serve at / (make build). Absent in development, where Vite serves it.
    ui_dir: Path = REPO_ROOT / "frontend" / "dist"

    @field_validator("ui_dir")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()


class Cli(BaseModel):
    # Paths to the claude / codex / gemini / tmux binaries; default is whatever is on PATH.
    claude_bin: str | None = None
    codex_bin: str | None = None
    gemini_bin: str | None = None
    tmux_bin: str | None = None
    # Extra environment for CLI calls, e.g. CLAUDE_CONFIG_DIR / CODEX_HOME to point the
    # CLIs at a sandbox. Point paths.* at the same place so reads match writes.
    env: dict[str, str] = {}
    timeout_s: float = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EYRIE_", env_nested_delimiter="__")

    paths: Paths = Paths()
    tools: Tools = Tools()
    sources: Sources = Sources()
    privacy: Privacy = Privacy()
    cli: Cli = Cli()
    server: Server = Server()
    sessions: Sessions = Sessions()
    # $/MTok per model id; merged over the built-in table in app/usage/prices.py
    pricing: dict[str, ModelPrice] = {}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, env_settings, TomlConfigSettingsSource(settings_cls, toml_file=active_config())


@lru_cache
def get_settings() -> Settings:
    return Settings()

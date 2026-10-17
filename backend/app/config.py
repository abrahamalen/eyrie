"""Settings from eyrie.toml (repo root, or $EYRIE_CONFIG), overridable with EYRIE_* env vars,
e.g. EYRIE_PATHS__VAULT=~/notes."""
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

REPO_ROOT = Path(__file__).resolve().parents[2]


def _config_file() -> Path:
    return Path(os.environ.get("EYRIE_CONFIG", REPO_ROOT / "eyrie.toml")).expanduser()


class Paths(BaseModel):
    model_config = ConfigDict(validate_default=True)

    claude_home: Path = Path("~/.claude")
    claude_json: Path = Path("~/.claude.json")
    codex_home: Path = Path("~/.codex")
    vault: Path = Path("~/workspace/Obsidian Vault")
    # Relative to the vault. Personal tasks only; the vault-root Tasks.md holds work tasks.
    tasks_file: Path = Path("Personal/Tasks.md")
    nexus_dir: Path = Path("agent-memory/Nexus")
    data_dir: Path = Path("~/.eyrie")

    @field_validator("*")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()

    @property
    def tasks(self) -> Path:
        return self.vault / self.tasks_file

    @property
    def nexus(self) -> Path:
        return self.vault / self.nexus_dir


class Sources(BaseModel):
    enabled: list[str] = ["claude", "codex", "mcp", "nexus", "tasks"]


class Privacy(BaseModel):
    hide_mcp: list[str] = []


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EYRIE_", env_nested_delimiter="__")

    paths: Paths = Paths()
    sources: Sources = Sources()
    privacy: Privacy = Privacy()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, env_settings, TomlConfigSettingsSource(settings_cls, toml_file=_config_file())


@lru_cache
def get_settings() -> Settings:
    return Settings()

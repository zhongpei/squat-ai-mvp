from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]
    root_dir: Path

    @property
    def session(self) -> dict[str, Any]:
        return self.raw.get("session", {})

    @property
    def stream(self) -> dict[str, Any]:
        return self.raw.get("stream", {})

    @property
    def perception(self) -> dict[str, Any]:
        return self.raw.get("perception", {})

    @property
    def biomechanics(self) -> dict[str, Any]:
        return self.raw.get("biomechanics", {})

    @property
    def alert(self) -> dict[str, Any]:
        return self.raw.get("alert", {})

    @property
    def ui(self) -> dict[str, Any]:
        return self.raw.get("ui", {})

    def resolve_path(self, value: str | Path) -> Path:
        p = Path(value)
        if p.is_absolute():
            return p
        return (self.root_dir / p).resolve()


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file does not exist: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a YAML mapping")
    root_dir = config_path.parent.parent if config_path.parent.name == "configs" else config_path.parent
    return AppConfig(raw=raw, root_dir=root_dir.resolve())


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"YAML file does not exist: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"YAML root must be a mapping: {p}")
    return data

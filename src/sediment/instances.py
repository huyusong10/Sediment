from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from sediment.settings import (
    CONFIG_RELATIVE_PATH,
    instance_root_from_config,
    load_settings_for_path,
)

_ACTIVE_REGISTRY_PATH: Path | None = None


def set_active_registry_path(path: str | Path | None) -> None:
    global _ACTIVE_REGISTRY_PATH
    _ACTIVE_REGISTRY_PATH = Path(path).expanduser().resolve() if path else None


def user_state_root() -> Path:
    if _ACTIVE_REGISTRY_PATH is not None:
        return _ACTIVE_REGISTRY_PATH.parent
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Sediment"
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "Sediment"
        return home / "AppData" / "Roaming" / "Sediment"
    xdg_state = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state:
        return Path(xdg_state) / "sediment"
    return home / ".local" / "state" / "sediment"


def instance_registry_path() -> Path:
    if _ACTIVE_REGISTRY_PATH is not None:
        return _ACTIVE_REGISTRY_PATH
    return user_state_root() / "instances.yaml"


def load_instance_registry() -> dict[str, Any]:
    path = instance_registry_path()
    if not path.exists():
        return {"version": 1, "instances": {}}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise RuntimeError(f"Sediment instance registry must be a mapping: {path}")
    payload.setdefault("version", 1)
    payload.setdefault("instances", {})
    if not isinstance(payload["instances"], dict):
        raise RuntimeError(f"Sediment instance registry has invalid instances payload: {path}")
    return payload


def save_instance_registry(payload: dict[str, Any]) -> Path:
    path = instance_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def register_instance(
    *,
    instance_name: str,
    config_path: str | Path,
    knowledge_name: str,
) -> dict[str, Any]:
    name = str(instance_name).strip()
    if not name:
        raise ValueError("instance_name must not be empty")
    config = Path(config_path).expanduser().resolve()
    root = instance_root_from_config(config)
    registry = load_instance_registry()
    existing = registry["instances"].get(name)
    if isinstance(existing, dict):
        existing_config = Path(str(existing.get("config_path", ""))).expanduser().resolve()
        if existing_config != config:
            raise ValueError(
                f"Sediment instance '{name}' is already registered at {existing_config}"
            )
    registry["instances"][name] = {
        "instance_name": name,
        "knowledge_name": str(knowledge_name).strip() or name,
        "instance_root": str(root),
        "config_path": str(config),
    }
    save_instance_registry(registry)
    return registry["instances"][name]


def unregister_instance(instance_name: str) -> dict[str, Any] | None:
    name = str(instance_name).strip()
    registry = load_instance_registry()
    removed = registry["instances"].pop(name, None)
    save_instance_registry(registry)
    return removed


def get_registered_instance(instance_name: str) -> dict[str, Any] | None:
    registry = load_instance_registry()
    entry = registry["instances"].get(str(instance_name).strip())
    if not isinstance(entry, dict):
        return None
    return dict(entry)


def resolve_registered_instance_config(instance_name: str) -> Path | None:
    entry = get_registered_instance(instance_name)
    if entry is None:
        return None
    return Path(entry["config_path"]).expanduser().resolve()


def list_registered_instances() -> list[dict[str, Any]]:
    registry = load_instance_registry()
    items: list[dict[str, Any]] = []
    for name, raw in sorted(registry["instances"].items()):
        if not isinstance(raw, dict):
            continue
        config_path = Path(str(raw.get("config_path", ""))).expanduser().resolve()
        instance_root = Path(str(raw.get("instance_root", ""))).expanduser().resolve()
        stale = not config_path.exists() or not instance_root.exists()
        payload = {
            "instance_name": name,
            "knowledge_name": str(raw.get("knowledge_name", name)),
            "config_path": str(config_path),
            "instance_root": str(instance_root),
            "stale": stale,
        }
        if config_path.exists():
            try:
                settings = load_settings_for_path(config_path)
            except Exception as exc:  # noqa: BLE001
                payload["load_error"] = str(exc)
                payload["stale"] = True
            else:
                payload["knowledge_name"] = settings["knowledge"]["name"]
                payload["port"] = settings["server"]["port"]
                payload["host"] = settings["server"]["host"]
                payload["kb_path"] = str(settings["paths"]["knowledge_base"])
        items.append(payload)
    return items


def find_ancestor_instance_config(target_root: str | Path) -> Path | None:
    root = Path(target_root).expanduser().resolve()
    for parent in root.parents:
        candidate = parent / CONFIG_RELATIVE_PATH
        if candidate.exists():
            return candidate.resolve()
    return None


def find_descendant_instance_configs(target_root: str | Path) -> list[Path]:
    root = Path(target_root).expanduser().resolve()
    matches: list[Path] = []
    for candidate in root.rglob("config.yaml"):
        candidate = candidate.resolve()
        if candidate == root / CONFIG_RELATIVE_PATH:
            continue
        if candidate.name != "config.yaml":
            continue
        if candidate.parent.name != "sediment":
            continue
        if candidate.parent.parent.name != "config":
            continue
        matches.append(candidate)
    return sorted(matches)

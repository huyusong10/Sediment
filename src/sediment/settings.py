from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Sequence

import yaml

from sediment.auth import normalize_auth_config

DEFAULT_CONFIG = {
    "version": 1,
    "locale": "en",
    "instance": {
        "name": "",
    },
    "paths": {
        "workspace_root": "../..",
        "knowledge_base": "knowledge-base",
        "state_dir": ".sediment_state",
        "db_path": None,
        "uploads_dir": None,
        "workspaces_dir": None,
    },
    "server": {
        "host": "0.0.0.0",
        "port": 8000,
        "sse_path": "/sediment/",
        "public_base_url": "",
        "run_jobs_in_process": False,
    },
    "auth": {
        "users": [],
        "admin_token": "",
        "session_secret": "",
        "admin_session_cookie_name": "sediment_admin_session",
        "admin_session_ttl_seconds": 43_200,
        "secure_cookies": False,
    },
    "network": {
        "trust_proxy_headers": False,
        "trusted_proxy_cidrs": [],
    },
    "submissions": {
        "rate_limit_count": 1,
        "rate_limit_window_seconds": 60,
        "dedupe_window_seconds": 86_400,
        "max_text_chars": 20_000,
        "max_upload_bytes": 10 * 1024 * 1024,
    },
    "jobs": {
        "max_attempts": 3,
        "stale_after_seconds": 900,
    },
    "agent": {
        "backend": "claude-code",
        "command": None,
        "model": None,
        "profile": None,
        "reasoning_effort": None,
        "sandbox": "workspace-write",
        "approval_policy": None,
        "permission_mode": None,
        "variant": None,
        "agent_name": None,
        "dangerously_skip_permissions": False,
        "extra_args": [],
        "doctor_timeout_seconds": 20,
        "exec_timeout_seconds": 240,
    },
    "knowledge": {
        "name": "Sediment Knowledge Base",
        "query_languages": "",
        "index": {
            "max_entries": 120,
            "max_tokens": 8000,
            "root_file": "index.root.md",
            "segment_glob": "index*.md",
        },
    },
}

_ACTIVE_CONFIG_PATH: Path | None = None
_SETTINGS_CACHE: dict[str, Any] | None = None
_SETTINGS_CACHE_KEY: tuple[str, float | None, str | None, tuple[tuple[str, str], ...]] | None = None
CONFIG_RELATIVE_PATH = Path("config") / "sediment" / "config.yaml"
ENV_OVERRIDE_KEYS = {
    "SEDIMENT_HOST": ("server", "host"),
    "SEDIMENT_PORT": ("server", "port"),
    "SEDIMENT_PUBLIC_BASE_URL": ("server", "public_base_url"),
    "SEDIMENT_KB_PATH": ("paths", "knowledge_base"),
    "SEDIMENT_STATE_DIR": ("paths", "state_dir"),
    "SEDIMENT_DB_PATH": ("paths", "db_path"),
    "SEDIMENT_UPLOADS_DIR": ("paths", "uploads_dir"),
    "SEDIMENT_WORKSPACES_DIR": ("paths", "workspaces_dir"),
}


def package_root() -> Path:
    return Path(__file__).resolve().parent


def source_root() -> Path:
    return package_root().parent


def set_active_config_path(path: str | Path | None) -> None:
    global _ACTIVE_CONFIG_PATH
    _ACTIVE_CONFIG_PATH = Path(path).expanduser() if path else None
    clear_settings_cache()


def clear_settings_cache() -> None:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_KEY
    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_KEY = None


def current_config_path() -> Path:
    explicit = _ACTIVE_CONFIG_PATH or _argv_config_path(sys.argv[1:])
    if explicit is not None:
        return explicit.expanduser().resolve()

    local = discover_local_config_path()
    if local is not None:
        return local
    return (Path.cwd() / CONFIG_RELATIVE_PATH).resolve()


def load_settings() -> dict[str, Any]:
    return load_settings_for_path(
        current_config_path(),
        argv=sys.argv[1:],
    )


def load_settings_for_path(
    config_path: str | Path,
    *,
    argv: Sequence[str] | None = None,
) -> dict[str, Any]:
    global _SETTINGS_CACHE, _SETTINGS_CACHE_KEY
    resolved_config_path = Path(config_path).expanduser().resolve()
    argv = argv if argv is not None else []
    cache_key = (
        str(resolved_config_path),
        resolved_config_path.stat().st_mtime if resolved_config_path.exists() else None,
        _argv_run_jobs_override(argv),
        _env_override_signature(),
    )
    if _SETTINGS_CACHE is not None and _SETTINGS_CACHE_KEY == cache_key:
        return copy.deepcopy(_SETTINGS_CACHE)

    merged = copy.deepcopy(DEFAULT_CONFIG)
    file_payload: dict[str, Any] = {}
    config_exists = resolved_config_path.exists()
    if config_exists:
        loaded = yaml.safe_load(resolved_config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise RuntimeError(f"Sediment config must be a mapping: {resolved_config_path}")
        file_payload = loaded
        _deep_merge(merged, loaded)

    _apply_environment_overrides(merged)
    merged["auth"] = normalize_auth_config(merged.get("auth"))

    instance_root = instance_root_from_config(resolved_config_path)
    workspace_root = _resolve_path(
        merged["paths"].get("workspace_root", "../.."),
        base=resolved_config_path.parent,
    )
    knowledge_base = _resolve_path(
        merged["paths"].get("knowledge_base", "knowledge-base"),
        base=workspace_root,
    )
    state_dir = _resolve_path(
        merged["paths"].get("state_dir", ".sediment_state"),
        base=workspace_root,
    )
    db_path = _resolve_path_or_default(
        merged["paths"].get("db_path"),
        default=state_dir / "platform.db",
        base=workspace_root,
    )
    uploads_dir = _resolve_path_or_default(
        merged["paths"].get("uploads_dir"),
        default=state_dir / "uploads",
        base=workspace_root,
    )
    workspaces_dir = _resolve_path_or_default(
        merged["paths"].get("workspaces_dir"),
        default=state_dir / "workspaces",
        base=workspace_root,
    )

    merged["locale"] = _normalize_locale(merged.get("locale", "en"))
    merged["instance"]["name"] = str(merged["instance"].get("name", "")).strip()
    if not merged["instance"]["name"]:
        merged["instance"]["name"] = instance_root.name or "sediment-instance"
    merged["agent"]["backend"] = normalize_agent_backend(merged["agent"].get("backend", ""))
    merged["agent"]["extra_args"] = _string_list(merged["agent"].get("extra_args", []))
    merged["agent"]["command"] = _normalize_command_value(merged["agent"].get("command"))
    merged["auth"]["admin_session_ttl_seconds"] = max(
        300,
        _to_int(merged["auth"].get("admin_session_ttl_seconds"), 43_200),
    )
    merged["server"]["port"] = _to_int(merged["server"].get("port"), 8000)
    merged["server"]["sse_path"] = _normalize_sse_path(
        merged["server"].get("sse_path", "/sediment/")
    )
    merged["server"]["public_base_url"] = _normalize_public_base_url(
        merged["server"].get("public_base_url", "")
    )
    merged["server"]["run_jobs_in_process"] = _to_bool(
        merged["server"].get("run_jobs_in_process"),
        False,
    )
    override_run_jobs = _argv_run_jobs_override(argv)
    if override_run_jobs is not None:
        merged["server"]["run_jobs_in_process"] = override_run_jobs == "true"
    merged["network"]["trusted_proxy_cidrs"] = _string_list(
        merged["network"].get("trusted_proxy_cidrs", [])
    )
    merged["submissions"]["rate_limit_count"] = max(
        1,
        _to_int(merged["submissions"].get("rate_limit_count"), 1),
    )
    merged["submissions"]["rate_limit_window_seconds"] = max(
        1,
        _to_int(merged["submissions"].get("rate_limit_window_seconds"), 60),
    )
    merged["submissions"]["dedupe_window_seconds"] = max(
        0,
        _to_int(merged["submissions"].get("dedupe_window_seconds"), 86_400),
    )
    merged["submissions"]["max_text_chars"] = max(
        256,
        _to_int(merged["submissions"].get("max_text_chars"), 20_000),
    )
    merged["submissions"]["max_upload_bytes"] = max(
        1_024,
        _to_int(merged["submissions"].get("max_upload_bytes"), 10 * 1024 * 1024),
    )
    merged["jobs"]["max_attempts"] = max(1, _to_int(merged["jobs"].get("max_attempts"), 3))
    merged["jobs"]["stale_after_seconds"] = max(
        0,
        _to_int(merged["jobs"].get("stale_after_seconds"), 900),
    )
    merged["knowledge"]["name"] = str(merged["knowledge"].get("name", "")).strip()
    if not merged["knowledge"]["name"]:
        merged["knowledge"]["name"] = merged["instance"]["name"]
    merged["knowledge"]["query_languages"] = str(
        merged["knowledge"].get("query_languages", "")
    ).strip()
    merged["knowledge"]["index"]["max_entries"] = max(
        1,
        _to_int(merged["knowledge"]["index"].get("max_entries"), 120),
    )
    merged["knowledge"]["index"]["max_tokens"] = max(
        1,
        _to_int(merged["knowledge"]["index"].get("max_tokens"), 8000),
    )
    merged["knowledge"]["index"]["root_file"] = str(
        merged["knowledge"]["index"].get("root_file", "index.root.md")
    ).strip() or "index.root.md"
    merged["knowledge"]["index"]["segment_glob"] = str(
        merged["knowledge"]["index"].get("segment_glob", "index*.md")
    ).strip() or "index*.md"

    override_run_jobs = _argv_run_jobs_override(argv)
    if override_run_jobs is not None:
        merged["server"]["run_jobs_in_process"] = override_run_jobs == "true"

    merged["config_path"] = resolved_config_path
    merged["config_exists"] = config_exists
    merged["instance_root"] = instance_root
    merged["workspace_root"] = workspace_root
    merged["paths"]["knowledge_base"] = knowledge_base
    merged["paths"]["state_dir"] = state_dir
    merged["paths"]["db_path"] = db_path
    merged["paths"]["uploads_dir"] = uploads_dir
    merged["paths"]["workspaces_dir"] = workspaces_dir
    merged["paths"]["workspace_root"] = workspace_root
    merged["raw"] = file_payload

    _SETTINGS_CACHE = copy.deepcopy(merged)
    _SETTINGS_CACHE_KEY = cache_key
    return merged


def normalize_agent_backend(value: str) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "claude": "claude-code",
        "claude-code": "claude-code",
        "codex": "codex",
        "codex-cli": "codex",
        "opencode": "opencode",
        "open-code": "opencode",
    }
    return aliases.get(raw, raw or "claude-code")


def discover_local_config_path(start: str | Path | None = None) -> Path | None:
    base = Path(start or Path.cwd()).expanduser().resolve()
    if base.is_file():
        base = base.parent
    for candidate_root in (base, *base.parents):
        candidate = candidate_root / CONFIG_RELATIVE_PATH
        if candidate.exists():
            return candidate.resolve()
    return None


def instance_root_from_config(config_path: str | Path) -> Path:
    path = Path(config_path).expanduser().resolve()
    if path.name == "config.yaml" and path.parent.name == "sediment":
        config_dir = path.parent.parent
        if config_dir.name == "config":
            return config_dir.parent.resolve()
    return path.parent.resolve()


def _argv_config_path(argv: Sequence[str]) -> Path | None:
    for index, token in enumerate(argv):
        if token == "--config" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if token.startswith("--config="):
            return Path(token.split("=", 1)[1])
    return None


def _argv_run_jobs_override(argv: Sequence[str]) -> str | None:
    for index, token in enumerate(argv):
        if token == "--run-jobs-in-process" and index + 1 < len(argv):
            return _normalize_bool_token(argv[index + 1])
        if token.startswith("--run-jobs-in-process="):
            return _normalize_bool_token(token.split("=", 1)[1])
    return None


def _env_override_signature() -> tuple[tuple[str, str], ...]:
    return tuple(
        (key, os.environ.get(key, "").strip())
        for key in ENV_OVERRIDE_KEYS
    )


def _apply_environment_overrides(target: dict[str, Any]) -> None:
    for env_key, path in ENV_OVERRIDE_KEYS.items():
        value = os.environ.get(env_key, "").strip()
        if not value:
            continue
        node: dict[str, Any] = target
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value


def _normalize_bool_token(value: str) -> str:
    return "true" if _to_bool(value, False) else "false"


def _resolve_path(value: str | Path, *, base: Path) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / candidate).resolve()


def _resolve_path_or_default(
    value: str | Path | None,
    *,
    default: Path,
    base: Path,
) -> Path:
    if value in {None, ""}:
        return default.resolve()
    return _resolve_path(value, base=base)


def _normalize_command_value(value: Any) -> str | list[str] | None:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in {None, ""}:
        return None
    return str(value)


def _normalize_locale(value: str) -> str:
    locale = str(value or "en").strip().lower()
    return locale if locale in {"en", "zh"} else "en"


def _normalize_sse_path(value: str) -> str:
    raw = str(value or "/sediment/").strip() or "/sediment/"
    if not raw.startswith("/"):
        raw = "/" + raw
    if not raw.endswith("/"):
        raw += "/"
    return raw


def _normalize_public_base_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw.rstrip("/")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value in {None, ""}:
        return []
    return [str(value)]


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if (
            key in target
            and isinstance(target[key], dict)
            and isinstance(value, dict)
        ):
            _deep_merge(target[key], value)
            continue
        target[key] = copy.deepcopy(value)

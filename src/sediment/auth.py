from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any

import yaml

VALID_ROLES = {"owner", "committer"}


def generate_token() -> str:
    return secrets.token_urlsafe(16)


def token_fingerprint(token: str) -> str:
    cleaned = str(token or "").strip()
    if not cleaned:
        return ""
    return cleaned[:4] + "..." + cleaned[-4:]


def normalize_role(value: str | None) -> str:
    role = str(value or "committer").strip().lower()
    return role if role in VALID_ROLES else "committer"


def auth_required(settings: dict[str, Any]) -> bool:
    return bool(active_users(settings))


def active_users(settings: dict[str, Any]) -> list[dict[str, Any]]:
    return [user for user in auth_users_from_settings(settings) if not user.get("disabled")]


def auth_users_from_settings(settings: dict[str, Any]) -> list[dict[str, Any]]:
    auth = settings.get("auth") or {}
    users = auth.get("users") or []
    if not isinstance(users, list):
        return []
    return [dict(user) for user in users if isinstance(user, dict)]


def find_user_by_token(settings: dict[str, Any], token: str) -> dict[str, Any] | None:
    cleaned = str(token or "").strip()
    if not cleaned:
        return None
    for user in auth_users_from_settings(settings):
        if user.get("disabled"):
            continue
        if str(user.get("token", "")).strip() == cleaned:
            return dict(user)
    return None


def find_user_by_id(settings: dict[str, Any], user_id: str) -> dict[str, Any] | None:
    target = str(user_id or "").strip()
    if not target:
        return None
    for user in auth_users_from_settings(settings):
        if str(user.get("id", "")).strip() == target:
            return dict(user)
    return None


def normalize_auth_config(raw_auth: Any) -> dict[str, Any]:
    auth = dict(raw_auth) if isinstance(raw_auth, dict) else {}
    raw_users = auth.get("users")
    normalized_users = _normalize_users(raw_users if isinstance(raw_users, list) else [])

    legacy_token = str(auth.get("admin_token", "")).strip()
    if legacy_token and not normalized_users:
        normalized_users.append(
            {
                "id": "owner",
                "name": "Owner",
                "role": "owner",
                "token": legacy_token,
                "created_at": "",
                "disabled": False,
            }
        )

    auth["users"] = normalized_users
    auth["admin_token"] = _primary_owner_token(normalized_users, fallback=legacy_token)
    auth["session_secret"] = str(auth.get("session_secret", "")).strip()
    auth["admin_session_cookie_name"] = (
        str(auth.get("admin_session_cookie_name", "")).strip() or "sediment_admin_session"
    )
    auth["admin_session_ttl_seconds"] = auth.get("admin_session_ttl_seconds", 43_200)
    auth["secure_cookies"] = bool(auth.get("secure_cookies", False))
    return auth


def create_user_record(
    *,
    name: str,
    role: str,
    created_at: str,
    token: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    cleaned_name = re.sub(r"\s+", " ", str(name or "").strip()) or "User"
    normalized_role = normalize_role(role)
    return {
        "id": str(user_id or f"user-{secrets.token_hex(4)}"),
        "name": cleaned_name,
        "role": normalized_role,
        "token": str(token or generate_token()).strip(),
        "created_at": str(created_at or "").strip(),
        "disabled": False,
    }


def persist_normalized_auth(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    payload = _load_config_payload(path)
    payload["auth"] = normalize_auth_config(payload.get("auth"))
    _write_config_payload(path, payload)
    return payload


def list_config_users(config_path: str | Path) -> list[dict[str, Any]]:
    payload = persist_normalized_auth(config_path)
    return auth_users_from_settings({"auth": payload.get("auth", {})})


def create_config_user(
    config_path: str | Path,
    *,
    name: str,
    role: str,
    created_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(config_path).expanduser().resolve()
    payload = persist_normalized_auth(path)
    auth = payload.get("auth") or {}
    users = auth.get("users") or []
    if normalize_role(role) == "owner":
        raise ValueError("owner account is created during init and cannot be added later")
    record = create_user_record(name=name, role=role, created_at=created_at)
    users.append(record)
    auth["users"] = _normalize_users(users)
    auth["admin_token"] = _primary_owner_token(auth["users"], fallback=auth.get("admin_token", ""))
    payload["auth"] = auth
    _write_config_payload(path, payload)
    return payload, record


def disable_config_user(config_path: str | Path, user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = Path(config_path).expanduser().resolve()
    payload = persist_normalized_auth(path)
    auth = payload.get("auth") or {}
    users = auth.get("users") or []
    updated_user: dict[str, Any] | None = None
    for user in users:
        if str(user.get("id", "")).strip() != str(user_id or "").strip():
            continue
        user["disabled"] = True
        updated_user = dict(user)
        break
    if updated_user is None:
        raise FileNotFoundError(f"user not found: {user_id}")
    auth["users"] = _normalize_users(users)
    auth["admin_token"] = _primary_owner_token(auth["users"], fallback=auth.get("admin_token", ""))
    payload["auth"] = auth
    _write_config_payload(path, payload)
    return payload, updated_user


def _normalize_users(raw_users: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    owner_seen = False
    for index, raw_user in enumerate(raw_users):
        if not isinstance(raw_user, dict):
            continue
        token = str(raw_user.get("token", "")).strip()
        if not token:
            continue
        normalized_role = normalize_role(raw_user.get("role"))
        if normalized_role == "owner":
            if owner_seen:
                normalized_role = "committer"
            else:
                owner_seen = True
        user_id = str(raw_user.get("id", "")).strip() or (
            "owner" if normalized_role == "owner" else f"user-{index + 1}"
        )
        if user_id in seen_ids:
            user_id = f"{user_id}-{index + 1}"
        seen_ids.add(user_id)
        normalized.append(
            {
                "id": user_id,
                "name": re.sub(r"\s+", " ", str(raw_user.get("name", "")).strip()) or user_id,
                "role": normalized_role,
                "token": token,
                "created_at": str(raw_user.get("created_at", "")).strip(),
                "disabled": bool(raw_user.get("disabled", False)),
            }
        )
    return normalized


def _primary_owner_token(users: list[dict[str, Any]], *, fallback: str) -> str:
    for user in users:
        if user.get("disabled"):
            continue
        if user.get("role") == "owner":
            return str(user.get("token", "")).strip()
    return str(fallback or "").strip()


def _load_config_payload(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return payload if isinstance(payload, dict) else {}


def _write_config_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

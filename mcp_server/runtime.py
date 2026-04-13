from __future__ import annotations

from pathlib import Path

from mcp_server.agent_runner import get_agent_runner
from mcp_server.platform_services import ensure_platform_state, parse_trusted_proxy_cidrs
from mcp_server.platform_store import PlatformStore
from mcp_server.settings import load_settings
from mcp_server.settings import project_root as settings_project_root


def project_root() -> Path:
    return settings_project_root()


def default_kb_path() -> Path:
    return project_root() / "knowledge-base"


def kb_path() -> Path:
    return Path(load_settings()["paths"]["knowledge_base"])


def instance_root() -> Path:
    return Path(load_settings()["instance_root"])


def instance_name() -> str:
    return str(load_settings()["instance"]["name"])


def knowledge_name() -> str:
    return str(load_settings()["knowledge"]["name"])


def config_path() -> Path:
    return Path(load_settings()["config_path"])


def host() -> str:
    return str(load_settings()["server"]["host"])


def port() -> int:
    return int(load_settings()["server"]["port"])


def sse_endpoint() -> str:
    return str(load_settings()["server"]["sse_path"])


def admin_token() -> str:
    return str(load_settings()["auth"]["admin_token"]).strip()


def session_secret() -> str:
    return str(load_settings()["auth"]["session_secret"]).strip()


def admin_session_cookie_name() -> str:
    value = str(load_settings()["auth"]["admin_session_cookie_name"]).strip()
    return value or "sediment_admin_session"


def admin_session_ttl_seconds() -> int:
    return int(load_settings()["auth"]["admin_session_ttl_seconds"])


def secure_cookies() -> bool:
    return bool(load_settings()["auth"]["secure_cookies"])


def trust_proxy_headers() -> bool:
    return bool(load_settings()["network"]["trust_proxy_headers"])


def trusted_proxy_cidrs():
    return parse_trusted_proxy_cidrs(",".join(load_settings()["network"]["trusted_proxy_cidrs"]))


def submission_rate_limit_count() -> int:
    return int(load_settings()["submissions"]["rate_limit_count"])


def submission_rate_limit_window_seconds() -> int:
    return int(load_settings()["submissions"]["rate_limit_window_seconds"])


def submission_dedupe_window_seconds() -> int:
    return int(load_settings()["submissions"]["dedupe_window_seconds"])


def max_text_submission_chars() -> int:
    return int(load_settings()["submissions"]["max_text_chars"])


def max_upload_bytes() -> int:
    return int(load_settings()["submissions"]["max_upload_bytes"])


def job_max_attempts() -> int:
    return int(load_settings()["jobs"]["max_attempts"])


def job_stale_after_seconds() -> int:
    return int(load_settings()["jobs"]["stale_after_seconds"])


def run_jobs_in_process() -> bool:
    return bool(load_settings()["server"]["run_jobs_in_process"])


def platform_paths() -> dict[str, Path]:
    settings = load_settings()
    state_dir = Path(settings["paths"]["state_dir"])
    return {
        "state_dir": state_dir,
        "db_path": Path(settings["paths"]["db_path"]),
        "uploads_dir": Path(settings["paths"]["uploads_dir"]),
        "workspaces_dir": Path(settings["paths"]["workspaces_dir"]),
        "run_dir": state_dir / "run",
        "log_dir": state_dir / "logs",
    }


def build_store() -> PlatformStore:
    paths = platform_paths()
    store = PlatformStore(paths["db_path"])
    ensure_platform_state(
        store=store,
        state_dir=paths["state_dir"],
        uploads_dir=paths["uploads_dir"],
        workspaces_dir=paths["workspaces_dir"],
    )
    paths["run_dir"].mkdir(parents=True, exist_ok=True)
    paths["log_dir"].mkdir(parents=True, exist_ok=True)
    return store


def build_agent_runner(*, store: PlatformStore | None = None):
    store = store or build_store()
    return get_agent_runner(
        project_root=project_root(),
        kb_path=kb_path(),
        workspaces_dir=platform_paths()["workspaces_dir"],
        store=store,
    )

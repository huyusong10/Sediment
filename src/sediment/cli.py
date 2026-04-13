from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from sediment import launcher, worker
from sediment.control import (
    apply_review_decision,
    enqueue_tidy_job,
    platform_status_payload,
    resolve_tidy_issue,
    review_detail_payload,
    submit_document_request,
    submit_text_request,
)
from sediment.instances import (
    find_ancestor_instance_config,
    find_descendant_instance_configs,
    get_registered_instance,
    instance_registry_path,
    list_registered_instances,
    register_instance,
    resolve_registered_instance_config,
    set_active_registry_path,
    unregister_instance,
)
from sediment.kb import inventory, resolve_kb_document_path
from sediment.llm_cli import (
    build_cli_command,
    collect_output,
    help_command,
    parse_json_object,
    resolve_executable,
)
from sediment.platform_services import get_health_payload, list_reviews_with_jobs
from sediment.runtime import (
    admin_token,
    build_store,
    config_path,
    host,
    instance_name,
    instance_root,
    job_max_attempts,
    job_stale_after_seconds,
    kb_path,
    knowledge_name,
    max_text_submission_chars,
    max_upload_bytes,
    platform_paths,
    port,
    project_root,
    run_jobs_in_process,
    sse_endpoint,
    submission_dedupe_window_seconds,
    submission_rate_limit_count,
    submission_rate_limit_window_seconds,
    trust_proxy_headers,
    trusted_proxy_cidrs,
)
from sediment.settings import (
    CONFIG_RELATIVE_PATH,
    current_config_path,
    discover_local_config_path,
    load_settings,
    load_settings_for_path,
    set_active_config_path,
    source_root,
)


def scoped_command(command: str) -> str:
    local = discover_local_config_path()
    current = current_config_path()
    if local is not None and local.resolve() == current.resolve():
        return f"sediment {command}"
    return f"sediment --instance {instance_name()} {command}"


def print_next_steps(*steps: str) -> None:
    if not steps:
        return
    print("")
    print("Next:")
    for step in steps:
        print(f"- {step}")


def progress_enabled(args) -> bool:
    return not getattr(args, "json", False) and not getattr(args, "quiet", False)


def cli_progress(message: str, *, enabled: bool = True) -> None:
    if enabled:
        print(f"[sediment] {message}")


def cli_supports_color() -> bool:
    return (
        sys.stdout.isatty()
        and os.environ.get("NO_COLOR") is None
        and os.environ.get("TERM", "").lower() != "dumb"
    )


def cli_style(text: str, *, color: str | None = None, bold: bool = False) -> str:
    if not cli_supports_color():
        return text
    colors = {
        "red": "31",
        "green": "32",
        "yellow": "33",
        "blue": "34",
        "cyan": "36",
    }
    codes: list[str] = []
    if bold:
        codes.append("1")
    if color in colors:
        codes.append(colors[color])
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def doctor_badge(item: dict[str, Any]) -> str:
    if bool(item.get("ok")):
        label = "OK"
        color = "green"
    elif item.get("severity") == "warning":
        label = "WARN"
        color = "yellow"
    else:
        label = "FAIL"
        color = "red"
    return cli_style(label, color=color, bold=True)


def summarize_text(text: str, *, limit: int = 120) -> str:
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _run_agent_simple_probe(
    settings: dict[str, Any],
    *,
    backend: str,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    prompt = "You are Sediment doctor. Reply with OK only."
    timeout_seconds = int(settings["agent"]["doctor_timeout_seconds"])
    last_preview = ""
    for attempt in (1, 2):
        progress(
            "Running simple "
            f"{backend} generation probe "
            f"(timeout: {timeout_seconds}s, attempt {attempt}/2)."
        )
        with tempfile.TemporaryDirectory(prefix="sediment-doctor-") as temp_dir:
            temp_root = Path(temp_dir)
            invocation = build_cli_command(
                settings,
                prompt,
                prompt_file=temp_root / "prompt.txt",
                payload_file=temp_root / "payload.json",
                skill_file=temp_root / "skill.md",
                cwd=temp_root,
            )
            started_at = time.perf_counter()
            try:
                result = subprocess.run(
                    invocation.command,
                    input=invocation.stdin_data,
                    cwd=str(temp_root),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                last_preview = f"Timed out after {timeout_seconds}s"
                if attempt == 2:
                    return {
                        "ok": False,
                        "detail": f"Agent probe timed out after {timeout_seconds}s.",
                        "duration_ms": duration_ms,
                        "preview": last_preview,
                    }
                progress("Probe timed out; retrying once.")
                continue

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            raw_output = collect_output(
                invocation,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            preview = summarize_text(raw_output or f"exit code {result.returncode}")
            last_preview = preview
            if result.returncode != 0:
                if attempt == 2:
                    return {
                        "ok": False,
                        "detail": f"Agent probe failed: {preview}",
                        "duration_ms": duration_ms,
                        "preview": preview,
                    }
                progress("Probe returned a non-zero exit status; retrying once.")
                continue
            if raw_output.strip():
                return {
                    "ok": True,
                    "detail": f"Agent responded to a simple generation probe: {preview}",
                    "duration_ms": duration_ms,
                    "backend": backend,
                }
            if attempt == 2:
                return {
                    "ok": False,
                    "detail": "Agent probe returned an empty response.",
                    "duration_ms": duration_ms,
                    "preview": preview,
                }
            progress("Probe returned an empty response; retrying once.")

    return {
        "ok": False,
        "detail": f"Agent probe failed: {last_preview or 'unknown error'}",
        "duration_ms": None,
        "preview": last_preview,
    }


def _run_agent_structured_probe(
    settings: dict[str, Any],
    *,
    backend: str,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    schema = json.dumps(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "ok": {"type": "boolean"},
                "backend": {"type": "string"},
            },
            "required": ["ok", "backend"],
        }
    )
    prompt = (
        "You are Sediment doctor. Return JSON only with "
        f'{{"ok": true, "backend": "{backend}"}} and no extra text.'
    )
    timeout_seconds = int(settings["agent"]["doctor_timeout_seconds"])
    last_preview = ""
    for attempt in (1, 2):
        progress(
            "Running structured "
            f"{backend} generation probe "
            f"(timeout: {timeout_seconds}s, attempt {attempt}/2)."
        )
        with tempfile.TemporaryDirectory(prefix="sediment-doctor-") as temp_dir:
            temp_root = Path(temp_dir)
            invocation = build_cli_command(
                settings,
                prompt,
                prompt_file=temp_root / "prompt.txt",
                payload_file=temp_root / "payload.json",
                skill_file=temp_root / "skill.md",
                cwd=temp_root,
                extra_args=["--json-schema", schema],
            )
            started_at = time.perf_counter()
            try:
                result = subprocess.run(
                    invocation.command,
                    input=invocation.stdin_data,
                    cwd=str(temp_root),
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                last_preview = f"Timed out after {timeout_seconds}s"
                if attempt == 2:
                    return {
                        "ok": False,
                        "detail": f"Structured probe timed out after {timeout_seconds}s.",
                        "duration_ms": duration_ms,
                        "preview": last_preview,
                    }
                progress("Structured probe timed out; retrying once.")
                continue

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            raw_output = collect_output(
                invocation,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            preview = summarize_text(raw_output or f"exit code {result.returncode}")
            last_preview = preview
            if result.returncode != 0:
                if attempt == 2:
                    return {
                        "ok": False,
                        "detail": f"Structured probe failed: {preview}",
                        "duration_ms": duration_ms,
                        "preview": preview,
                    }
                progress("Structured probe returned a non-zero exit status; retrying once.")
                continue
            try:
                payload = parse_json_object(raw_output)
            except RuntimeError:
                if attempt == 2:
                    return {
                        "ok": False,
                        "detail": "Agent CLI did not return a JSON object.",
                        "duration_ms": duration_ms,
                        "preview": preview,
                    }
                progress("Structured probe returned non-JSON output; retrying once.")
                continue

            ok = bool(payload.get("ok")) and str(payload.get("backend", "")).strip()
            if ok:
                returned_backend = str(payload.get("backend", backend))
                return {
                    "ok": True,
                    "detail": (
                        "Structured probe succeeded for backend "
                        f"{returned_backend}."
                    ),
                    "duration_ms": duration_ms,
                    "backend": returned_backend,
                }
            if attempt == 2:
                return {
                    "ok": False,
                    "detail": f"Structured probe returned an unexpected payload: {preview}",
                    "duration_ms": duration_ms,
                    "preview": preview,
                }
            progress("Structured probe payload was incomplete; retrying once.")

    return {
        "ok": False,
        "detail": f"Structured probe failed: {last_preview or 'unknown error'}",
        "duration_ms": None,
        "preview": last_preview,
    }


def doctor_status(checks: list[dict[str, Any]]) -> str:
    if any(not item["ok"] and item.get("severity", "error") == "error" for item in checks):
        return "failed"
    if any(not item["ok"] for item in checks):
        return "warn"
    return "ok"


def daemon_paths() -> dict[str, Path]:
    paths = platform_paths()
    paths["run_dir"].mkdir(parents=True, exist_ok=True)
    paths["log_dir"].mkdir(parents=True, exist_ok=True)
    return {
        "pid": paths["run_dir"] / "platform.pid",
        "meta": paths["run_dir"] / "platform.json",
        "log": paths["log_dir"] / "platform.log",
    }


def local_health_url() -> str:
    bind_host = host()
    query_host = "127.0.0.1" if bind_host in {"0.0.0.0", "::", "[::]"} else bind_host
    return f"http://{query_host}:{port()}/healthz"


def current_actor_name() -> str:
    return (
        os.environ.get("SEDIMENT_ACTOR")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "cli"
    )


def _server_module():
    from sediment import server as server_module

    return server_module


def _apply_config_path_from_argv(argv: list[str] | None) -> None:
    if not argv:
        return
    for index, token in enumerate(argv):
        if token == "--config" and index + 1 < len(argv):
            set_active_config_path(argv[index + 1])
            return
        if token.startswith("--config="):
            set_active_config_path(token.split("=", 1)[1])
            return


def _apply_registry_path_from_argv(argv: list[str] | None) -> None:
    if not argv:
        return
    for index, token in enumerate(argv):
        if token == "--registry" and index + 1 < len(argv):
            set_active_registry_path(argv[index + 1])
            return
        if token.startswith("--registry="):
            set_active_registry_path(token.split("=", 1)[1])
            return


def _resolve_cli_context(args) -> None:
    if getattr(args, "registry", None):
        set_active_registry_path(args.registry)

    if getattr(args, "config", None):
        set_active_config_path(args.config)
        return

    instance = getattr(args, "instance", None)
    if instance:
        config = resolve_registered_instance_config(instance)
        if config is None:
            raise FileNotFoundError(
                f"Sediment instance '{instance}' is not registered. "
                "Run `sediment instance list` to inspect known instances."
            )
        set_active_config_path(config)
        return

    set_active_config_path(current_config_path())


def _platform_paths_from_settings(settings: dict[str, Any]) -> dict[str, Path]:
    state_dir = Path(settings["paths"]["state_dir"])
    return {
        "state_dir": state_dir,
        "db_path": Path(settings["paths"]["db_path"]),
        "uploads_dir": Path(settings["paths"]["uploads_dir"]),
        "workspaces_dir": Path(settings["paths"]["workspaces_dir"]),
        "run_dir": state_dir / "run",
        "log_dir": state_dir / "logs",
    }


def _daemon_paths_for_settings(settings: dict[str, Any]) -> dict[str, Path]:
    paths = _platform_paths_from_settings(settings)
    return {
        "pid": paths["run_dir"] / "platform.pid",
        "meta": paths["run_dir"] / "platform.json",
        "log": paths["log_dir"] / "platform.log",
    }


def _health_url_for_settings(settings: dict[str, Any]) -> str:
    bind_host = str(settings["server"]["host"])
    query_host = "127.0.0.1" if bind_host in {"0.0.0.0", "::", "[::]"} else bind_host
    return f"http://{query_host}:{int(settings['server']['port'])}/healthz"


def _daemon_status_for_settings(settings: dict[str, Any]) -> dict[str, Any]:
    paths = _daemon_paths_for_settings(settings)
    metadata: dict[str, Any] = {}
    if paths["meta"].exists():
        try:
            metadata = json.loads(paths["meta"].read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metadata = {}
    pid = int(metadata.get("pid", 0)) if str(metadata.get("pid", "")).isdigit() else None
    running = bool(pid and is_pid_running(pid))
    health_url = _health_url_for_settings(settings)
    health: dict[str, Any] | None = None
    try:
        with urllib.request.urlopen(health_url, timeout=1.0) as response:
            health = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        health = None
    return {
        "running": running,
        "pid": pid,
        "stale_pid": bool(pid and not running),
        "log_path": str(paths["log"]),
        "meta_path": str(paths["meta"]),
        "pid_path": str(paths["pid"]),
        "health_url": health_url,
        "health": health,
        "metadata": metadata,
    }


def _slugify_instance_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-_.").lower()
    return slug or "sediment-instance"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _should_run_init_wizard(args) -> bool:
    if getattr(args, "json", False):
        return False
    interactive = getattr(args, "interactive", None)
    if interactive is not None:
        return bool(interactive)
    return sys.stdin.isatty() and sys.stdout.isatty()


def _prompt_init_value(
    label: str,
    default: str,
    *,
    validate: Callable[[str], str] | None = None,
) -> str:
    while True:
        raw_value = input(f"{label} [{default}]: ").strip()
        if not raw_value or raw_value.lower() == "skip":
            return default
        if validate is None:
            return raw_value
        try:
            return validate(raw_value)
        except ValueError as exc:
            print(f"  {exc}")


def _prompt_init_yes_no(label: str, *, default: bool) -> bool:
    default_token = "Y/n" if default else "y/N"
    while True:
        raw_value = input(f"{label} [{default_token}]: ").strip().lower()
        if not raw_value or raw_value == "skip":
            return default
        if raw_value in {"y", "yes"}:
            return True
        if raw_value in {"n", "no"}:
            return False
        print("  Please answer yes or no.")


def _parse_init_port(value: str) -> str:
    number = int(value)
    if number < 1 or number > 65535:
        raise ValueError("Port must be between 1 and 65535.")
    return str(number)


def _parse_init_backend(value: str) -> str:
    candidate = value.strip().lower()
    choices = {"claude-code", "codex", "opencode"}
    if candidate not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"Backend must be one of: {allowed}.")
    return candidate


def _parse_init_host(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Host must not be empty.")
    return candidate


def _run_init_wizard(
    *,
    target_root: Path,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    print(cli_style("Sediment init wizard", color="cyan", bold=True))
    print("Press Enter to keep the suggested value. Type `skip` to do the same explicitly.")
    print("Host and port prompts already show their defaults, so Enter accepts them immediately.")
    print(f"Working directory: {target_root}")
    print("")

    instance_label = _prompt_init_value(
        "Instance name",
        str(defaults["instance_name"]),
    )
    knowledge_label = _prompt_init_value(
        "Knowledge name",
        str(defaults["knowledge_name"]),
    )
    backend = _prompt_init_value(
        "Agent backend (claude-code/codex/opencode)",
        str(defaults["backend"]),
        validate=_parse_init_backend,
    )
    host_value = _prompt_init_value(
        "Bind host",
        str(defaults["host"]),
        validate=_parse_init_host,
    )
    port_value = int(
        _prompt_init_value(
            "Bind port",
            str(defaults["port"]),
            validate=_parse_init_port,
        )
    )
    create_kb = _prompt_init_yes_no(
        "Create knowledge-base scaffold",
        default=bool(defaults["create_kb"]),
    )
    print("")
    return {
        "instance_name": instance_label,
        "knowledge_name": knowledge_label,
        "backend": backend,
        "host": host_value,
        "port": port_value,
        "create_kb": create_kb,
    }


def _detect_available_backend() -> str | None:
    for backend in ("claude-code", "codex", "opencode"):
        settings = {"agent": {"backend": backend, "command": None}}
        if resolve_executable(settings):
            return backend
    return None


def _write_instance_scaffold(
    *,
    target_root: Path,
    config_target: Path,
    instance_label: str,
    knowledge_label: str,
    backend: str,
    host_value: str,
    port_value: int,
    create_kb: bool,
) -> dict[str, Any]:
    import yaml

    config_target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "locale": "en",
        "instance": {
            "name": instance_label,
        },
        "paths": {
            "workspace_root": "../..",
            "knowledge_base": "knowledge-base",
            "state_dir": ".sediment_state",
        },
        "server": {
            "host": host_value,
            "port": int(port_value),
            "sse_path": "/sediment/",
            "run_jobs_in_process": False,
        },
        "auth": {
            "admin_token": secrets.token_urlsafe(16),
            "session_secret": secrets.token_urlsafe(24),
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
            "backend": backend,
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
            "name": knowledge_label,
            "query_languages": "",
            "index": {
                "max_entries": 120,
                "max_tokens": 8000,
                "root_file": "index.root.md",
                "segment_glob": "index*.md",
            },
        },
    }
    config_target.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    state_dir = target_root / ".sediment_state"
    state_dir.mkdir(parents=True, exist_ok=True)

    if not create_kb:
        return payload

    kb_root = target_root / "knowledge-base"
    (kb_root / "entries").mkdir(parents=True, exist_ok=True)
    (kb_root / "placeholders").mkdir(parents=True, exist_ok=True)
    (kb_root / "indexes").mkdir(parents=True, exist_ok=True)
    index_root = kb_root / "index.root.md"
    if not index_root.exists():
        index_root.write_text(
            "\n".join(
                [
                    "---",
                    "kind: index",
                    "segment: root",
                    "---",
                    "# Index Root",
                    "",
                    "- [[index.core]]",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    core_index = kb_root / "indexes" / "index.core.md"
    if not core_index.exists():
        core_index.write_text(
            "\n".join(
                [
                    "---",
                    "kind: index",
                    "segment: core",
                    "---",
                    f"# {knowledge_label}",
                    "",
                    "Add your first formal entries here.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    return payload


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    state = _pid_state(pid)
    if state and state.startswith("Z"):
        return False
    return True


def _pid_state(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    state = result.stdout.strip()
    return state or None


def read_daemon_metadata() -> dict[str, Any]:
    paths = daemon_paths()
    if not paths["meta"].exists():
        return {}
    try:
        return json.loads(paths["meta"].read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_daemon_metadata(payload: dict[str, Any]) -> None:
    paths = daemon_paths()
    paths["meta"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["pid"].write_text(str(payload["pid"]) + "\n", encoding="utf-8")


def clear_daemon_metadata() -> None:
    paths = daemon_paths()
    paths["pid"].unlink(missing_ok=True)
    paths["meta"].unlink(missing_ok=True)


def daemon_status() -> dict[str, Any]:
    paths = daemon_paths()
    metadata = read_daemon_metadata()
    pid = int(metadata.get("pid", 0)) if str(metadata.get("pid", "")).isdigit() else None
    running = bool(pid and is_pid_running(pid))
    if pid and not running:
        metadata["stale_pid"] = True
    health: dict[str, Any] | None = None
    try:
        with urllib.request.urlopen(local_health_url(), timeout=1.2) as response:
            health = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        health = None
    return {
        "running": running,
        "pid": pid,
        "stale_pid": bool(pid and not running),
        "log_path": str(paths["log"]),
        "meta_path": str(paths["meta"]),
        "pid_path": str(paths["pid"]),
        "health_url": local_health_url(),
        "health": health,
        "metadata": metadata,
    }


def wait_for_health(*, timeout_seconds: float) -> bool:
    deadline = time.time() + max(timeout_seconds, 0.2)
    while time.time() < deadline:
        status = daemon_status()
        if status["health"] and status["health"].get("status") == "ok":
            return True
        time.sleep(0.2)
    return False


def tail_lines(path: Path, *, limit: int) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-max(1, limit) :]


def stop_running_daemon(*, timeout_seconds: float, force_kill: bool) -> int:
    status = daemon_status()
    if not status["running"]:
        if status["stale_pid"]:
            clear_daemon_metadata()
        print("Sediment daemon is not running.")
        return 0

    pid = int(status["pid"])
    print(f"Stopping Sediment daemon (pid={pid})...")
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + max(timeout_seconds, 0.5)
    while time.time() < deadline:
        if not is_pid_running(pid):
            clear_daemon_metadata()
            print("Sediment daemon stopped.")
            return 0
        time.sleep(0.2)

    if force_kill:
        print("Graceful stop timed out; sending SIGKILL.")
        os.kill(pid, signal.SIGKILL)
        time.sleep(0.3)
        clear_daemon_metadata()
        return 0

    print("Timed out waiting for the daemon to stop.", file=sys.stderr)
    return 1


def start_daemon(args) -> int:
    enabled = progress_enabled(args)
    cli_progress(
        f"Starting Sediment daemon for instance `{instance_name()}`.",
        enabled=enabled,
    )
    errors = launcher.validate_environment(require_cli=True)
    if errors and not args.skip_checks:
        print("Cannot start Sediment daemon:", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 2

    status = daemon_status()
    if status["running"]:
        if not args.force:
            print("Sediment daemon is already running.", file=sys.stderr)
            return 1
        stop_result = stop_running_daemon(
            timeout_seconds=args.shutdown_timeout,
            force_kill=True,
        )
        if stop_result != 0:
            return stop_result
    elif status["stale_pid"]:
        clear_daemon_metadata()

    paths = daemon_paths()
    cli_progress(f"Launching background services. Logs: {paths['log']}", enabled=enabled)
    command = [
        sys.executable,
        "-m",
        "sediment.cli",
        "--config",
        str(current_config_path()),
        "__run-platform-daemon",
        "--worker-poll-interval",
        str(args.worker_poll_interval),
        "--startup-timeout",
        str(args.startup_timeout),
    ]
    if args.skip_checks:
        command.append("--skip-checks")

    with paths["log"].open("a", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(project_root()),
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "PYTHONPATH": (
                    f"{source_root()}{os.pathsep}{os.environ.get('PYTHONPATH', '').strip()}"
                    if os.environ.get("PYTHONPATH", "").strip()
                    else str(source_root())
                ),
            },
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    write_daemon_metadata(
        {
            "pid": process.pid,
            "command": command,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "port": port(),
            "host": host(),
            "log_path": str(paths["log"]),
        }
    )

    cli_progress("Waiting for the health endpoint to become ready.", enabled=enabled)
    if wait_for_health(timeout_seconds=args.startup_timeout):
        print(f"Sediment daemon started (pid={process.pid}).")
        print(f"Portal: {local_health_url().removesuffix('/healthz')}/portal")
        print(f"Admin:  {local_health_url().removesuffix('/healthz')}/admin")
        print(f"Logs:   {paths['log']}")
        print_next_steps(
            f"Open the portal: {local_health_url().removesuffix('/healthz')}/portal",
            f"Open the admin UI: {local_health_url().removesuffix('/healthz')}/admin",
            f"Inspect status: {scoped_command('status')}",
        )
        return 0

    if process.poll() is not None:
        print("Sediment daemon exited during startup.", file=sys.stderr)
    else:
        print("Sediment daemon did not become healthy before timeout.", file=sys.stderr)
        try:
            os.kill(process.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            process.wait(timeout=max(args.shutdown_timeout, 1.0))
        except subprocess.TimeoutExpired:
            try:
                os.kill(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait(timeout=1.0)
    clear_daemon_metadata()
    lines = tail_lines(paths["log"], limit=30)
    if lines:
        print("--- recent log ---", file=sys.stderr)
        print("\n".join(lines), file=sys.stderr)
    return 1


def server_run(args) -> int:
    cli_progress(
        f"Running Sediment in the foreground for instance `{instance_name()}`.",
        enabled=progress_enabled(args),
    )
    argv = [
        "--worker-poll-interval",
        str(args.worker_poll_interval),
        "--startup-timeout",
        str(args.startup_timeout),
    ]
    if args.skip_checks:
        argv.append("--skip-checks")
    return launcher.main(argv)


def server_stop(args) -> int:
    return stop_running_daemon(
        timeout_seconds=args.shutdown_timeout,
        force_kill=args.force_kill,
    )


def server_restart(args) -> int:
    stop_result = stop_running_daemon(
        timeout_seconds=args.shutdown_timeout,
        force_kill=True,
    )
    if stop_result != 0:
        return stop_result
    return start_daemon(args)


def server_logs(args) -> int:
    lines = tail_lines(Path(daemon_paths()["log"]), limit=args.lines)
    if not lines:
        print("No daemon log is available yet.")
        return 0
    print("\n".join(lines))
    return 0


def render_daemon_status(status: dict[str, Any]) -> str:
    health = status.get("health") or {}
    health_text = health.get("status", "unreachable") if health else "unreachable"
    return "\n".join(
        [
            f"running: {status['running']}",
            f"pid: {status.get('pid') or '-'}",
            f"health: {health_text}",
            f"log: {status['log_path']}",
            f"health_url: {status['health_url']}",
        ]
    )


def server_status(args) -> int:
    status = daemon_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(render_daemon_status(status))
    return 0


def kb_explore(args) -> int:
    cli_progress(
        f"Exploring the knowledge base for: {args.question}",
        enabled=progress_enabled(args),
    )
    result = _server_module().answer_question(
        args.question,
        kb_path().resolve(),
        project_root(),
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(result.get("answer", ""))
    print(f"confidence: {result.get('confidence', 'unknown')}")
    if result.get("sources"):
        print("sources: " + ", ".join(result["sources"]))
    return 0


def kb_health(args) -> int:
    payload = get_health_payload(kb_path())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    summary = payload["summary"]
    print("Health summary")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    print(f"- issues: {len(payload['issues'])}")
    for item in payload["issues"][: args.limit]:
        print(f"* [{item['severity']}] {item['target']}: {item['summary']}")
    return 0


def kb_list(args) -> int:
    data = inventory(kb_path())
    names = sorted(set(data["entries"]) | set(data["placeholders"]) | set(data.get("indexes", [])))
    if args.json:
        print(json.dumps(names, ensure_ascii=False, indent=2))
        return 0
    print("\n".join(names))
    return 0


def kb_read(args) -> int:
    path = resolve_kb_document_path(kb_path(), args.name)
    if path is None:
        print(f"Entry '{args.name}' not found.", file=sys.stderr)
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def kb_tidy(args) -> int:
    enabled = progress_enabled(args)
    cli_progress(f"Resolving tidy issue for `{args.target}`.", enabled=enabled)
    store = build_store()
    issue = resolve_tidy_issue(
        kb_path=kb_path(),
        target=args.target,
        issue_type=args.issue_type,
    )
    cli_progress(f"Queueing tidy job for issue type `{issue['type']}`.", enabled=enabled)
    job = enqueue_tidy_job(
        store=store,
        kb_path=kb_path(),
        issue=issue,
        actor_name=args.actor_name or current_actor_name(),
        max_attempts=job_max_attempts(),
    )
    if args.process_once:
        cli_progress("Processing the queued tidy job immediately.", enabled=enabled)
        worker.process_queue_until_idle(max_jobs=1)
        job = store.get_job(job["id"]) or job

    if args.json:
        print(json.dumps({"job": job, "issue": issue}, ensure_ascii=False, indent=2))
    else:
        print(f"Created tidy job: {job['id']}")
        print(f"target: {issue['target']}")
        print(f"type: {issue['type']}")
        print(f"status: {job['status']}")
        if not args.process_once:
            print(
                "The job is queued. Start the daemon or run "
                "`sediment server run` / `sediment up` to process it."
            )
    return 0


def submit_text_command(args) -> int:
    enabled = progress_enabled(args)
    content = args.content
    if not content and args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8")
    if not content and not sys.stdin.isatty():
        content = sys.stdin.read()
    if not content:
        print("Text submission content is required.", file=sys.stderr)
        return 1

    try:
        cli_progress(f"Submitting text draft `{args.title}` to the buffer.", enabled=enabled)
        record = submit_text_request(
            store=build_store(),
            title=args.title,
            content=content,
            submitter_name=args.submitter_name or current_actor_name(),
            submitter_ip="127.0.0.1",
            submission_type=args.submission_type,
            submitter_user_id="cli",
            rate_limit_count=submission_rate_limit_count(),
            rate_limit_window_seconds=submission_rate_limit_window_seconds(),
            max_text_chars=max_text_submission_chars(),
            dedupe_window_seconds=submission_dedupe_window_seconds(),
        )
    except (PermissionError, FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(f"Created submission: {record['id']}")
        print(f"title: {record['title']}")
        print(f"status: {record['status']}")
        print_next_steps(
            scoped_command("status"),
            scoped_command("review list"),
        )
    return 0


def submit_file_command(args) -> int:
    enabled = progress_enabled(args)
    file_path = Path(args.path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        print(f"File not found: {file_path}", file=sys.stderr)
        return 1

    try:
        cli_progress(f"Uploading document `{file_path.name}` to the buffer.", enabled=enabled)
        record = submit_document_request(
            store=build_store(),
            uploads_dir=platform_paths()["uploads_dir"],
            filename=args.filename or file_path.name,
            mime_type=args.mime_type,
            file_bytes=file_path.read_bytes(),
            submitter_name=args.submitter_name or current_actor_name(),
            submitter_ip="127.0.0.1",
            submitter_user_id="cli",
            rate_limit_count=submission_rate_limit_count(),
            rate_limit_window_seconds=submission_rate_limit_window_seconds(),
            max_upload_bytes=max_upload_bytes(),
            dedupe_window_seconds=submission_dedupe_window_seconds(),
        )
    except (PermissionError, FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(f"Created submission: {record['id']}")
        print(f"title: {record['title']}")
        print(f"status: {record['status']}")
        print_next_steps(
            scoped_command("status"),
            scoped_command("review list"),
        )
    return 0


def status_command(args) -> int:
    store = build_store()
    status = platform_status_payload(
        store=store,
        kb_path=kb_path(),
        paths=platform_paths(),
        daemon=daemon_status(),
        instance_name=instance_name(),
        knowledge_name=knowledge_name(),
        instance_root=instance_root(),
        config_path=config_path(),
        host=host(),
        port=port(),
        sse_endpoint=sse_endpoint(),
        auth_required=bool(admin_token()),
        run_jobs_in_process=run_jobs_in_process(),
        submission_rate_limit_count=submission_rate_limit_count(),
        submission_rate_limit_window_seconds=submission_rate_limit_window_seconds(),
        submission_dedupe_window_seconds=submission_dedupe_window_seconds(),
        max_text_submission_chars=max_text_submission_chars(),
        max_upload_bytes=max_upload_bytes(),
        job_max_attempts=job_max_attempts(),
        job_stale_after_seconds=job_stale_after_seconds(),
        trust_proxy_headers=trust_proxy_headers(),
        trusted_proxy_cidrs=[str(item) for item in trusted_proxy_cidrs()],
    )
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    daemon = status["daemon"]
    overview = status["overview"]
    queue = status["queue"]
    print("Sediment status")
    print(f"- instance: {status['instance']['name']}")
    print(f"- knowledge: {status['instance']['knowledge_name']}")
    print(f"- config: {status['instance']['config_path']}")
    print(f"- daemon_running: {daemon['running']}")
    print(f"- daemon_pid: {daemon.get('pid') or '-'}")
    daemon_health = (
        daemon.get("health", {}).get("status", "unreachable")
        if daemon.get("health")
        else "unreachable"
    )
    print(f"- health: {daemon_health}")
    print(f"- pending_submissions: {queue['pending_submissions']}")
    print(f"- queued_jobs: {queue['queued_jobs']}")
    print(f"- running_jobs: {queue['running_jobs']}")
    print(f"- pending_reviews: {queue['pending_reviews']}")
    print(f"- blocking_issues: {overview['severity_counts'].get('blocking', 0)}")
    print(f"- kb_path: {status['paths']['kb_path']}")
    print(f"- portal: {status['urls']['portal']}")
    print(f"- admin: {status['urls']['admin']}")
    print(f"- mcp: {status['urls']['mcp_sse']}")
    if not daemon["running"]:
        print_next_steps(scoped_command("server start"))
    elif queue["pending_reviews"] or queue["pending_submissions"]:
        print_next_steps(
            scoped_command("review list"),
            scoped_command("logs show --component worker --lines 80"),
        )
    return 0


def status_queue_command(args) -> int:
    store = build_store()
    payload = platform_status_payload(
        store=store,
        kb_path=kb_path(),
        paths=platform_paths(),
        daemon=daemon_status(),
        instance_name=instance_name(),
        knowledge_name=knowledge_name(),
        instance_root=instance_root(),
        config_path=config_path(),
        host=host(),
        port=port(),
        sse_endpoint=sse_endpoint(),
        auth_required=bool(admin_token()),
        run_jobs_in_process=run_jobs_in_process(),
        submission_rate_limit_count=submission_rate_limit_count(),
        submission_rate_limit_window_seconds=submission_rate_limit_window_seconds(),
        submission_dedupe_window_seconds=submission_dedupe_window_seconds(),
        max_text_submission_chars=max_text_submission_chars(),
        max_upload_bytes=max_upload_bytes(),
        job_max_attempts=job_max_attempts(),
        job_stale_after_seconds=job_stale_after_seconds(),
        trust_proxy_headers=trust_proxy_headers(),
        trusted_proxy_cidrs=[str(item) for item in trusted_proxy_cidrs()],
    )
    queue = payload["queue"]
    if args.json:
        print(json.dumps(queue, ensure_ascii=False, indent=2))
        return 0
    print("Queue status")
    for key, value in queue.items():
        print(f"- {key}: {value}")
    return 0


def status_health_command(args) -> int:
    payload = get_health_payload(kb_path())
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    summary = payload["summary"]
    print("KB health")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    print(f"- issues: {len(payload['issues'])}")
    return 0


def build_doctor_payload(
    progress: Callable[[str], None] | None = None,
    *,
    full: bool = False,
) -> dict[str, Any]:
    progress = progress or (lambda _message: None)
    progress("Loading instance configuration.")
    settings = load_settings()
    checks: list[dict[str, Any]] = []
    notes: list[str] = []

    def record(
        name: str,
        ok: bool,
        detail: str,
        *,
        severity: str = "error",
        **extra: Any,
    ) -> None:
        checks.append(
            {
                "name": name,
                "ok": ok,
                "detail": detail,
                "severity": severity,
                **extra,
            }
        )

    config_path = current_config_path()
    record(
        "config.file",
        bool(settings.get("config_exists")),
        f"Using config file: {config_path}",
        severity="error",
        path=str(config_path),
    )

    configured_instance_root = instance_root()
    record(
        "paths.instance_root",
        configured_instance_root.exists() and configured_instance_root.is_dir(),
        f"instance_root={configured_instance_root}",
        severity="error",
        path=str(configured_instance_root),
    )

    progress("Checking knowledge base path.")
    configured_kb = kb_path()
    record(
        "paths.knowledge_base",
        configured_kb.exists() and configured_kb.is_dir(),
        f"knowledge_base={configured_kb}",
        severity="error",
        path=str(configured_kb),
    )

    progress("Checking registry path.")
    registry_path = instance_registry_path()
    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        if registry_path.exists():
            registry_path.read_text(encoding="utf-8")
        else:
            probe = registry_path.parent / ".doctor-registry-write-check"
            probe.write_text("ok\n", encoding="utf-8")
            probe.unlink(missing_ok=True)
        record(
            "paths.registry",
            True,
            f"registry={registry_path}",
            severity="error",
            path=str(registry_path),
        )
    except OSError as exc:
        record(
            "paths.registry",
            False,
            f"registry is not writable: {exc}",
            severity="error",
            path=str(registry_path),
        )

    progress("Checking writable state directory.")
    state_dir = platform_paths()["state_dir"]
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        probe = state_dir / ".doctor-write-check"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        record(
            "paths.state_dir",
            True,
            f"state_dir is writable: {state_dir}",
            severity="error",
            path=str(state_dir),
        )
    except OSError as exc:
        record(
            "paths.state_dir",
            False,
            f"state_dir is not writable: {exc}",
            severity="error",
            path=str(state_dir),
        )

    progress("Checking configured server port.")
    daemon = daemon_status()
    bind_host = host()
    bind_port = port()
    if daemon["running"]:
        record(
            "server.port",
            True,
            f"Port {bind_port} is already serving the current Sediment daemon.",
            severity="error",
            host=bind_host,
            port=bind_port,
        )
    else:
        try:
            family = (
                socket.AF_INET6
                if ":" in bind_host and "." not in bind_host
                else socket.AF_INET
            )
            bind_target: tuple[Any, ...]
            if family == socket.AF_INET6:
                bind_target = (bind_host, bind_port, 0, 0)
            else:
                bind_target = (bind_host, bind_port)
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(bind_target)
            record(
                "server.port",
                True,
                f"Port {bind_port} is available on host {bind_host}.",
                severity="error",
                host=bind_host,
                port=bind_port,
            )
        except OSError as exc:
            record(
                "server.port",
                False,
                f"Port {bind_port} is not available on host {bind_host}: {exc}",
                severity="error",
                host=bind_host,
                port=bind_port,
            )

    backend = settings["agent"]["backend"]
    progress(f"Resolving agent backend executable for {backend}.")
    executable = resolve_executable(settings)
    record(
        "agent.executable",
        bool(executable),
        (
            f"Resolved backend executable for {backend}: {executable}"
            if executable
            else f"Could not resolve executable for backend {backend}"
        ),
        severity="error",
        backend=backend,
        executable=executable,
    )

    if executable:
        try:
            progress(f"Running `{backend} --help` probe (timeout: 10s).")
            started_at = time.perf_counter()
            result = subprocess.run(
                help_command(settings),
                cwd=str(project_root()),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            ok = result.returncode == 0
            preview = summarize_text(result.stderr.strip() or result.stdout.strip())
            if ok:
                detail = "Help command responded successfully."
            else:
                detail = f"Help command failed: {preview or f'exit code {result.returncode}'}"
            record(
                "agent.help",
                ok,
                detail,
                severity="warning",
                backend=backend,
                duration_ms=duration_ms,
                preview=preview,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            record(
                "agent.help",
                False,
                f"Failed to run help command: {exc}",
                severity="warning",
                backend=backend,
            )

        simple_probe = _run_agent_simple_probe(
            settings,
            backend=backend,
            progress=progress,
        )
        record(
            "agent.simple_probe",
            bool(simple_probe["ok"]),
            str(simple_probe["detail"]),
            severity="error",
            backend=str(simple_probe.get("backend", backend)),
            duration_ms=simple_probe.get("duration_ms"),
            preview=simple_probe.get("preview"),
        )
        if full:
            structured_probe = _run_agent_structured_probe(
                settings,
                backend=backend,
                progress=progress,
            )
            record(
                "agent.structured_probe",
                bool(structured_probe["ok"]),
                str(structured_probe["detail"]),
                severity="warning",
                backend=str(structured_probe.get("backend", backend)),
                duration_ms=structured_probe.get("duration_ms"),
                preview=structured_probe.get("preview"),
            )
            if not structured_probe["ok"]:
                notes.append(
                    "The backend still passed the simple probe, so normal prompts work. "
                    "Only the stricter structured JSON probe was unstable, which may affect "
                    "tidy, ingest, and other schema-driven workflows."
                )
        else:
            notes.append(
                "Structured JSON probe skipped in quick mode. "
                f"Run `{scoped_command('doctor --full')}` if ingest, tidy, or "
                "other structured workflows feel unstable."
            )
    else:
        notes.append(
            "Agent probes were skipped because the configured backend executable "
            "could not be resolved."
        )

    return {
        "status": doctor_status(checks),
        "mode": "full" if full else "quick",
        "config_path": str(config_path),
        "instance_name": settings["instance"]["name"],
        "knowledge_name": settings["knowledge"]["name"],
        "backend": backend,
        "checks": checks,
        "notes": notes,
    }


def doctor_command(args) -> int:
    enabled = progress_enabled(args)
    cli_progress(
        f"Running doctor for instance `{instance_name()}`.",
        enabled=enabled,
    )
    payload = build_doctor_payload(
        progress=lambda message: cli_progress(message, enabled=enabled),
        full=bool(args.full),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] != "failed" else 1

    overall_map = {
        "ok": ("PASS", "green"),
        "warn": ("WARN", "yellow"),
        "failed": ("FAIL", "red"),
    }
    overall_label, overall_color = overall_map[payload["status"]]
    overall = cli_style(overall_label, color=overall_color, bold=True)
    print(cli_style("Sediment doctor", color="cyan", bold=True))
    print(f"status: {overall}")
    print(f"mode: {payload['mode']}")
    print(f"instance: {payload['instance_name']}")
    print(f"knowledge: {payload['knowledge_name']}")
    print(f"backend: {payload['backend']}")
    print(f"config: {payload['config_path']}")
    print("")
    print(cli_style("Checks", bold=True))
    for item in payload["checks"]:
        duration = ""
        if item.get("duration_ms") is not None:
            duration = f" ({item['duration_ms']}ms)"
        print(f"{doctor_badge(item):>4}  {item['name']}{duration}")
        print(f"      {item['detail']}")
    if payload.get("notes"):
        print("")
        print(cli_style("Notes", bold=True))
        for note in payload["notes"]:
            print(f"- {note}")
    blocked = [
        item["name"]
        for item in payload["checks"]
        if not item["ok"] and item.get("severity", "error") == "error"
    ]
    warnings = [
        item["name"]
        for item in payload["checks"]
        if not item["ok"] and item.get("severity", "error") == "warning"
    ]
    if blocked or warnings:
        print("")
        print(cli_style("Next", bold=True))
        if blocked:
            print(f"- Fix the blocking checks above: {', '.join(blocked)}")
        if warnings:
            print(f"- Review the warning checks above: {', '.join(warnings)}")
        re_run = "doctor --json" if payload["mode"] == "quick" else "doctor --full --json"
        print(f"- Re-run machine-readable diagnostics: {scoped_command(re_run)}")
    return 0 if payload["status"] != "failed" else 1


def init_command(args) -> int:
    enabled = progress_enabled(args)
    target_root = Path.cwd().resolve()
    config_target = target_root / CONFIG_RELATIVE_PATH
    cli_progress(f"Initializing Sediment instance in {target_root}.", enabled=enabled)

    if config_target.exists() and not args.force:
        print(
            f"Sediment is already initialized here: {config_target}",
            file=sys.stderr,
        )
        return 1

    if not args.allow_nested:
        ancestor = find_ancestor_instance_config(target_root)
        if ancestor is not None:
            print(
                "Refusing to create a nested Sediment instance inside "
                f"{ancestor.parent.parent.parent}. Use --allow-nested to override.",
                file=sys.stderr,
            )
            return 2
        descendants = find_descendant_instance_configs(target_root)
        if descendants:
            print(
                "Refusing to create a parent Sediment instance over existing child instances. "
                f"First child config: {descendants[0]}",
                file=sys.stderr,
            )
            return 2

    detected_backend = _detect_available_backend()
    backend_default = args.backend or detected_backend or "claude-code"
    if args.backend:
        cli_progress(f"Using requested backend `{args.backend}`.", enabled=enabled)
    elif detected_backend:
        cli_progress(
            f"Detected available agent backend `{detected_backend}`.",
            enabled=enabled,
        )
    else:
        cli_progress(
            "No installed agent backend was detected; defaulting to `claude-code` in the scaffold.",
            enabled=enabled,
        )
    host_value = args.host or "127.0.0.1"
    port_value = args.port or _pick_free_port()
    create_kb = not args.no_kb

    defaults = {
        "instance_name": args.instance_name or _slugify_instance_name(target_root.name),
        "knowledge_name": args.knowledge_name or f"{target_root.name} Knowledge Base",
        "backend": backend_default,
        "host": host_value,
        "port": port_value,
        "create_kb": create_kb,
    }

    if _should_run_init_wizard(args):
        try:
            wizard = _run_init_wizard(target_root=target_root, defaults=defaults)
        except (EOFError, KeyboardInterrupt):
            print("\nSediment init cancelled.", file=sys.stderr)
            return 130
        instance_label = wizard["instance_name"]
        knowledge_label = wizard["knowledge_name"]
        backend = wizard["backend"]
        host_value = wizard["host"]
        port_value = int(wizard["port"])
        create_kb = bool(wizard["create_kb"])
    else:
        instance_label = str(defaults["instance_name"])
        knowledge_label = str(defaults["knowledge_name"])
        backend = str(defaults["backend"])

    existing = get_registered_instance(instance_label)
    if existing is not None:
        existing_config = Path(existing["config_path"]).expanduser().resolve()
        if existing_config != config_target.resolve():
            print(
                f"Instance name '{instance_label}' is already registered at {existing_config}.",
                file=sys.stderr,
            )
            return 1

    cli_progress(f"Using backend `{backend}`.", enabled=enabled)

    cli_progress(f"Writing instance scaffold to {config_target}.", enabled=enabled)
    scaffold = _write_instance_scaffold(
        target_root=target_root,
        config_target=config_target,
        instance_label=instance_label,
        knowledge_label=knowledge_label,
        backend=backend,
        host_value=host_value,
        port_value=port_value,
        create_kb=create_kb,
    )
    cli_progress("Registering instance in the local registry.", enabled=enabled)
    register_instance(
        instance_name=instance_label,
        config_path=config_target,
        knowledge_name=knowledge_label,
    )
    set_active_config_path(config_target)

    payload = {
        "instance_name": instance_label,
        "knowledge_name": knowledge_label,
        "config_path": str(config_target),
        "instance_root": str(target_root),
        "backend": backend,
        "host": host_value,
        "port": port_value,
        "knowledge_base_created": create_kb,
        "registry_path": str(instance_registry_path()),
        "admin_token": scaffold["auth"]["admin_token"],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("Sediment instance initialized")
    print(f"- instance: {instance_label}")
    print(f"- knowledge: {knowledge_label}")
    print(f"- root: {target_root}")
    print(f"- config: {config_target}")
    print(f"- backend: {backend}")
    print(f"- host: {host_value}")
    print(f"- port: {port_value}")
    print(f"- registry: {instance_registry_path()}")
    print(f"- admin_token: {scaffold['auth']['admin_token']}")
    print("- doctor: skipped during init")
    print(
        "Tip: if the agent backend, permissions, or port look suspicious, run "
        f"`{scoped_command('doctor')}`.",
    )
    print_next_steps(
        scoped_command("server start"),
        scoped_command("status"),
    )
    return 0


def instance_list_command(args) -> int:
    items = []
    for item in list_registered_instances():
        payload = dict(item)
        config = Path(item["config_path"])
        if config.exists():
            try:
                settings = load_settings_for_path(config)
            except Exception as exc:  # noqa: BLE001
                payload["load_error"] = str(exc)
            else:
                payload["daemon"] = _daemon_status_for_settings(settings)
        items.append(payload)

    if args.json:
        print(json.dumps({"instances": items}, ensure_ascii=False, indent=2))
        return 0

    if not items:
        print("No Sediment instances are registered.")
        return 0

    print("Sediment instances")
    for item in items:
        running = item.get("daemon", {}).get("running", False)
        stale = " stale" if item.get("stale") else ""
        print(
            f"- {item['instance_name']}: {item['knowledge_name']} | "
            f"running={running} | port={item.get('port', '-')} | "
            f"root={item['instance_root']}{stale}"
        )
    return 0


def instance_show_command(args) -> int:
    entry = get_registered_instance(args.name)
    if entry is None:
        print(f"Sediment instance '{args.name}' is not registered.", file=sys.stderr)
        return 1
    payload = dict(entry)
    config = Path(entry["config_path"]).expanduser().resolve()
    if config.exists():
        settings = load_settings_for_path(config)
        payload["settings"] = {
            "instance_name": settings["instance"]["name"],
            "knowledge_name": settings["knowledge"]["name"],
            "port": settings["server"]["port"],
            "host": settings["server"]["host"],
            "kb_path": str(settings["paths"]["knowledge_base"]),
            "state_dir": str(settings["paths"]["state_dir"]),
        }
        payload["daemon"] = _daemon_status_for_settings(settings)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"instance: {payload['instance_name']}")
    print(f"knowledge: {payload.get('knowledge_name', payload['instance_name'])}")
    print(f"root: {payload['instance_root']}")
    print(f"config: {payload['config_path']}")
    if payload.get("settings"):
        print(f"port: {payload['settings']['port']}")
        print(f"kb_path: {payload['settings']['kb_path']}")
    if payload.get("daemon"):
        print(f"running: {payload['daemon']['running']}")
    return 0


def instance_remove_command(args) -> int:
    removed = unregister_instance(args.name)
    if removed is None:
        print(f"Sediment instance '{args.name}' is not registered.", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"removed": removed}, ensure_ascii=False, indent=2))
        return 0
    print(f"Removed instance registration: {args.name}")
    return 0


def review_list_command(args) -> int:
    store = build_store()
    reviews = list_reviews_with_jobs(store=store, decision=args.decision)[: args.limit]
    if args.json:
        print(json.dumps({"reviews": reviews}, ensure_ascii=False, indent=2))
        return 0

    if not reviews:
        print("No reviews matched the requested filter.")
        return 0

    print("Reviews")
    for item in reviews:
        job = item.get("job") or {}
        submission = item.get("submission") or {}
        target = submission.get("title") or job.get("target_entry_name") or "-"
        print(
            f"- {item['id']}: {job.get('job_type', '-')} | "
            f"target={target} | decision={item['decision']} | job={job.get('status', '-')}"
        )
    return 0


def review_show_command(args) -> int:
    try:
        payload = review_detail_payload(build_store(), args.review_id)
    except FileNotFoundError:
        print(f"Review '{args.review_id}' not found.", file=sys.stderr)
        return 1
    review = payload["review"]
    job = payload["job"]
    submission = payload.get("submission") or {}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"review: {review['id']}")
    print(f"decision: {review['decision']}")
    print(f"job: {job['id']} ({job['job_type']})")
    print(f"target: {submission.get('title') or job.get('target_entry_name') or '-'}")
    summary = (job.get("result_payload") or {}).get("summary", "")
    if summary:
        print(f"summary: {summary}")
    operations = (job.get("result_payload") or {}).get("operations", [])
    if operations:
        print("diff:")
        print("\n\n".join(str(item.get("diff", "")) for item in operations if item.get("diff")))
    return 0


def _review_decision_command(args, decision: str) -> int:
    store = build_store()
    try:
        cli_progress(
            f"Applying review decision `{decision}` to `{args.review_id}`.",
            enabled=progress_enabled(args),
        )
        payload = apply_review_decision(
            store=store,
            kb_path=kb_path(),
            review_id=args.review_id,
            decision=decision,
            reviewer_name=args.reviewer_name or current_actor_name(),
            comment=args.comment or "",
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Review {args.review_id} -> {decision}")
    print(f"job_status: {payload['job']['status']}")
    return 0


def review_approve_command(args) -> int:
    return _review_decision_command(args, "approve")


def review_reject_command(args) -> int:
    return _review_decision_command(args, "reject")


def _filter_log_lines(lines: list[str], component: str) -> list[str]:
    if component == "all":
        return lines
    prefix = f"[{component}]"
    return [line for line in lines if line.startswith(prefix)]


def logs_show_command(args) -> int:
    log_path = Path(daemon_paths()["log"])
    raw_lines = tail_lines(log_path, limit=max(args.lines * 4, args.lines))
    lines = _filter_log_lines(raw_lines, args.component)
    lines = lines[-args.lines :]
    if not lines:
        print("No matching log lines are available yet.")
        print_next_steps(scoped_command("server start"))
        return 0
    print("\n".join(lines))
    return 0


def logs_follow_command(args) -> int:
    log_path = Path(daemon_paths()["log"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    raw_lines = tail_lines(log_path, limit=max(args.lines * 4, args.lines))
    existing = _filter_log_lines(raw_lines, args.component)
    if existing:
        print("\n".join(existing[-args.lines :]))
    with log_path.open("a+", encoding="utf-8") as handle:
        handle.seek(0, os.SEEK_END)
        try:
            while True:
                line = handle.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                line = line.rstrip("\n")
                if args.component == "all" or line.startswith(f"[{args.component}]"):
                    print(line)
        except KeyboardInterrupt:
            return 0


def render_help(topic: str | None) -> str:
    topic = (topic or "overview").strip().lower()
    topics = {
        "overview": "\n".join(
            [
                "Sediment help",
                "",
                "Core workflow:",
                "  sediment init",
                "  sediment instance list",
                "  sediment doctor",
                "  sediment server start",
                "  sediment kb explore \"什么是热备份\"",
                "  sediment submit text --title \"新概念\" --content \"...\"",
                "  sediment review list",
                "  sediment logs follow",
                "",
                "Anywhere management:",
                "  sediment --instance ops-prod doctor",
                "  sediment --instance ops-prod server start",
                "  sediment --instance ops-prod review list",
                "",
                "Global options:",
                "  --instance NAME   use a registered instance from anywhere",
                "  --config PATH     point directly at one config.yaml",
                "",
                "Topics:",
                "  sediment help init",
                "  sediment help instance",
                "  sediment help config",
                "  sediment help review",
                "  sediment help logs",
                "  sediment help server",
                "  sediment help kb",
                "  sediment help submit",
                "  sediment help doctor",
            ]
        ),
        "init": "\n".join(
            [
                "sediment init",
                "",
                "Create a Sediment instance in the current directory.",
                "",
                "In a normal terminal, `sediment init` opens an interactive setup wizard.",
                "Press Enter to keep defaults, or pass --no-interactive for scripts and CI.",
                "If you work inside the instance root or its knowledge-base directory,",
                "Sediment resolves the local config automatically and you usually do not need",
                "`--instance`.",
                "",
                "Examples:",
                "  sediment init",
                "  sediment init --instance-name ops-prod --knowledge-name \"生产运维知识库\"",
                "  sediment init --backend codex --host 0.0.0.0 --port 8123 --no-interactive",
            ]
        ),
        "instance": "\n".join(
            [
                "sediment instance",
                "",
                "Manage the global registry of local Sediment instances.",
                "",
                "Commands:",
                "  sediment instance list",
                "  sediment instance show ops-prod",
                "  sediment instance remove ops-prod",
                "",
                "Most operational commands also accept `--instance NAME`.",
            ]
        ),
        "config": "\n".join(
            [
                "sediment config model",
                "",
                "Each instance stores its real runtime config in:",
                "  ./config/sediment/config.yaml",
                "",
                "Important fields:",
                "  instance.name   globally unique identifier for CLI management",
                "  knowledge.name  title shown in Portal/Admin",
                "  agent.backend   claude-code | codex | opencode",
                "",
                "Sediment no longer uses a global runtime config fallback. The only global",
                "state is the instance registry that maps instance names to local roots.",
            ]
        ),
        "review": "\n".join(
            [
                "sediment review",
                "",
                "Inspect and resolve pending review items without opening the web UI.",
                "",
                "Commands:",
                "  sediment review list",
                "  sediment review show <review-id>",
                "  sediment review approve <review-id> --reviewer-name alice",
                "  sediment review reject <review-id> "
                "--comment \"needs more evidence\"",
            ]
        ),
        "logs": "\n".join(
            [
                "sediment logs",
                "",
                "Read daemon logs for the current instance. Use --component all|server|worker|up.",
                "",
                "Commands:",
                "  sediment logs show --lines 80",
                "  sediment logs follow --component worker",
            ]
        ),
        "server": "\n".join(
            [
                "sediment server",
                "",
                "Manage the per-instance daemon lifecycle.",
                "",
                "Commands:",
                "  sediment server start",
                "  sediment server status",
                "  sediment server stop",
            ]
        ),
        "kb": "\n".join(
            [
                "sediment kb",
                "",
                "Explore and maintain the formal knowledge layer.",
                "",
                "Commands:",
                "  sediment kb list",
                "  sediment kb explore \"什么是热备份\"",
                "  sediment kb tidy \"薄弱条目\"",
            ]
        ),
        "doctor": "\n".join(
            [
                "sediment doctor",
                "",
                "Run a layered health check for the current Sediment instance.",
                "",
                "Quick mode checks config discovery, paths, port availability, executable",
                "resolution, CLI help, and a simple generation probe.",
                "",
                "Use `sediment doctor --full` to also run the stricter structured JSON probe",
                "used by tidy and other schema-driven workflows.",
            ]
        ),
        "submit": "\n".join(
            [
                "sediment submit",
                "",
                "Create buffered submissions from the CLI using the same backend logic",
                "as the Web portal and MCP tools.",
                "",
                "Commands:",
                "  sediment submit text --title \"新概念\" --content \"...\" --type concept",
                "  sediment submit text --title \"来自 stdin\" --type feedback < note.txt",
                "  sediment submit file ./incident.docx --name alice",
            ]
        ),
    }
    return topics.get(topic, topics["overview"])


def cli_help_command(args) -> int:
    print(render_help(args.topic))
    return 0


def run_platform_daemon(args) -> int:
    argv = [
        "--worker-poll-interval",
        str(args.worker_poll_interval),
        "--startup-timeout",
        str(args.startup_timeout),
    ]
    if args.skip_checks:
        argv.append("--skip-checks")
    return launcher.main(argv)


def legacy_up_main(argv: list[str] | None = None) -> int:
    _apply_registry_path_from_argv(argv)
    _apply_config_path_from_argv(argv)
    return launcher.main(argv)


def legacy_server_main(argv: list[str] | None = None) -> int:
    if argv:
        _apply_registry_path_from_argv(argv)
        _apply_config_path_from_argv(argv)
    return _server_module().main(argv)


def legacy_worker_main(argv: list[str] | None = None) -> int:
    _apply_registry_path_from_argv(argv)
    _apply_config_path_from_argv(argv)
    return worker.main(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sediment CLI for local instances, reviews, jobs, and knowledge workflows.",
        epilog="Try `sediment help` for task-oriented examples.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        help="Path to Sediment config.yaml. Defaults to ./config/sediment/config.yaml.",
    )
    parser.add_argument(
        "--instance",
        help="Use a registered Sediment instance by name.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress logs for non-JSON commands.",
    )
    parser.add_argument("--registry", help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a Sediment instance in the current directory.",
    )
    init_parser.add_argument("--instance-name")
    init_parser.add_argument("--knowledge-name")
    init_parser.add_argument(
        "--backend",
        choices=["claude-code", "codex", "opencode"],
        default=None,
    )
    init_parser.add_argument("--host", default=None)
    init_parser.add_argument("--port", type=int)
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument("--allow-nested", action="store_true")
    init_parser.add_argument("--no-kb", action="store_true")
    init_parser.add_argument(
        "--interactive",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Run an interactive init wizard in the terminal. Enabled by default on TTYs.",
    )
    init_parser.add_argument("--json", action="store_true")
    init_parser.set_defaults(func=init_command, needs_runtime_context=False)

    help_parser = subparsers.add_parser("help", help="Show Sediment task-oriented help.")
    help_parser.add_argument("topic", nargs="?")
    help_parser.set_defaults(func=cli_help_command, needs_runtime_context=False)

    up_parser = subparsers.add_parser("up", help="Run server + worker in the foreground.")
    up_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    up_parser.add_argument("--startup-timeout", type=float, default=10.0)
    up_parser.add_argument("--skip-checks", action="store_true")
    up_parser.set_defaults(func=server_run, needs_runtime_context=True)

    server_parser = subparsers.add_parser("server", help="Manage Sediment server/worker processes.")
    server_subparsers = server_parser.add_subparsers(dest="server_command", required=True)

    run_parser = server_subparsers.add_parser("run", help="Run server + worker in the foreground.")
    run_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    run_parser.add_argument("--startup-timeout", type=float, default=10.0)
    run_parser.add_argument("--skip-checks", action="store_true")
    run_parser.set_defaults(func=server_run, needs_runtime_context=True)

    start_parser = server_subparsers.add_parser("start", help="Start the platform daemon.")
    start_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    start_parser.add_argument("--startup-timeout", type=float, default=10.0)
    start_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    start_parser.add_argument("--skip-checks", action="store_true")
    start_parser.add_argument("--force", action="store_true")
    start_parser.set_defaults(func=start_daemon, needs_runtime_context=True)

    stop_parser = server_subparsers.add_parser("stop", help="Stop the platform daemon.")
    stop_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    stop_parser.add_argument("--force-kill", action="store_true")
    stop_parser.set_defaults(func=server_stop, needs_runtime_context=True)

    restart_parser = server_subparsers.add_parser("restart", help="Restart the platform daemon.")
    restart_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    restart_parser.add_argument("--startup-timeout", type=float, default=10.0)
    restart_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    restart_parser.add_argument("--skip-checks", action="store_true")
    restart_parser.set_defaults(func=server_restart, needs_runtime_context=True)

    status_parser = server_subparsers.add_parser("status", help="Show daemon status.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=server_status, needs_runtime_context=True)

    logs_parser = server_subparsers.add_parser("logs", help="Show recent daemon logs.")
    logs_parser.add_argument("--lines", type=int, default=60)
    logs_parser.set_defaults(func=server_logs, needs_runtime_context=True)

    kb_parser = subparsers.add_parser("kb", help="Knowledge-base operations.")
    kb_subparsers = kb_parser.add_subparsers(dest="kb_command", required=True)

    explore_parser = kb_subparsers.add_parser("explore", help="Ask a natural-language KB question.")
    explore_parser.add_argument("question")
    explore_parser.add_argument("--json", action="store_true")
    explore_parser.set_defaults(func=kb_explore, needs_runtime_context=True)

    health_parser = kb_subparsers.add_parser("health", help="Show KB health summary.")
    health_parser.add_argument("--json", action="store_true")
    health_parser.add_argument("--limit", type=int, default=10)
    health_parser.set_defaults(func=kb_health, needs_runtime_context=True)

    list_parser = kb_subparsers.add_parser("list", help="List KB entry names.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=kb_list, needs_runtime_context=True)

    read_parser = kb_subparsers.add_parser("read", help="Read a KB entry.")
    read_parser.add_argument("name")
    read_parser.set_defaults(func=kb_read, needs_runtime_context=True)

    tidy_parser = kb_subparsers.add_parser("tidy", help="Queue a tidy job for a KB target.")
    tidy_parser.add_argument("target")
    tidy_parser.add_argument("--issue-type")
    tidy_parser.add_argument("--actor-name")
    tidy_parser.add_argument("--process-once", action="store_true")
    tidy_parser.add_argument("--json", action="store_true")
    tidy_parser.set_defaults(func=kb_tidy, needs_runtime_context=True)

    review_parser = subparsers.add_parser("review", help="Inspect and resolve pending reviews.")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    review_list_parser = review_subparsers.add_parser("list", help="List reviews.")
    review_list_parser.add_argument("--decision", default="pending")
    review_list_parser.add_argument("--limit", type=int, default=20)
    review_list_parser.add_argument("--json", action="store_true")
    review_list_parser.set_defaults(func=review_list_command, needs_runtime_context=True)

    review_show_parser = review_subparsers.add_parser("show", help="Show one review.")
    review_show_parser.add_argument("review_id")
    review_show_parser.add_argument("--json", action="store_true")
    review_show_parser.set_defaults(func=review_show_command, needs_runtime_context=True)

    review_approve_parser = review_subparsers.add_parser("approve", help="Approve a review.")
    review_approve_parser.add_argument("review_id")
    review_approve_parser.add_argument("--reviewer-name")
    review_approve_parser.add_argument("--comment", default="")
    review_approve_parser.add_argument("--json", action="store_true")
    review_approve_parser.set_defaults(func=review_approve_command, needs_runtime_context=True)

    review_reject_parser = review_subparsers.add_parser("reject", help="Reject a review.")
    review_reject_parser.add_argument("review_id")
    review_reject_parser.add_argument("--reviewer-name")
    review_reject_parser.add_argument("--comment", default="")
    review_reject_parser.add_argument("--json", action="store_true")
    review_reject_parser.set_defaults(func=review_reject_command, needs_runtime_context=True)

    logs_parser = subparsers.add_parser("logs", help="Read daemon logs for the current instance.")
    logs_subparsers = logs_parser.add_subparsers(dest="logs_command", required=True)

    logs_show_parser = logs_subparsers.add_parser("show", help="Show recent log lines.")
    logs_show_parser.add_argument(
        "--component",
        choices=["all", "server", "worker", "up"],
        default="all",
    )
    logs_show_parser.add_argument("--lines", type=int, default=60)
    logs_show_parser.set_defaults(func=logs_show_command, needs_runtime_context=True)

    logs_tail_parser = logs_subparsers.add_parser("tail", help="Alias for logs show.")
    logs_tail_parser.add_argument(
        "--component",
        choices=["all", "server", "worker", "up"],
        default="all",
    )
    logs_tail_parser.add_argument("--lines", type=int, default=60)
    logs_tail_parser.set_defaults(func=logs_show_command, needs_runtime_context=True)

    logs_follow_parser = logs_subparsers.add_parser("follow", help="Follow daemon logs.")
    logs_follow_parser.add_argument(
        "--component",
        choices=["all", "server", "worker", "up"],
        default="all",
    )
    logs_follow_parser.add_argument("--lines", type=int, default=30)
    logs_follow_parser.set_defaults(func=logs_follow_command, needs_runtime_context=True)

    submit_parser = subparsers.add_parser(
        "submit",
        help="Create buffered submissions from the CLI.",
    )
    submit_subparsers = submit_parser.add_subparsers(dest="submit_command", required=True)

    submit_text_parser = submit_subparsers.add_parser("text", help="Submit plain text.")
    submit_text_parser.add_argument("--title", required=True)
    submit_text_parser.add_argument("--content")
    submit_text_parser.add_argument("--content-file")
    submit_text_parser.add_argument(
        "--type",
        dest="submission_type",
        choices=["text", "concept", "lesson", "feedback"],
        default="text",
    )
    submit_text_parser.add_argument("--name", dest="submitter_name")
    submit_text_parser.add_argument("--json", action="store_true")
    submit_text_parser.set_defaults(func=submit_text_command, needs_runtime_context=True)

    submit_file_parser = submit_subparsers.add_parser("file", help="Submit a document file.")
    submit_file_parser.add_argument("path")
    submit_file_parser.add_argument("--filename")
    submit_file_parser.add_argument("--mime-type")
    submit_file_parser.add_argument("--name", dest="submitter_name")
    submit_file_parser.add_argument("--json", action="store_true")
    submit_file_parser.set_defaults(func=submit_file_command, needs_runtime_context=True)

    instance_parser = subparsers.add_parser(
        "instance",
        help="Manage registered Sediment instances.",
    )
    instance_subparsers = instance_parser.add_subparsers(dest="instance_command", required=True)

    instance_list_parser = instance_subparsers.add_parser("list", help="List known instances.")
    instance_list_parser.add_argument("--json", action="store_true")
    instance_list_parser.set_defaults(func=instance_list_command, needs_runtime_context=False)

    instance_show_parser = instance_subparsers.add_parser("show", help="Show one instance.")
    instance_show_parser.add_argument("name")
    instance_show_parser.add_argument("--json", action="store_true")
    instance_show_parser.set_defaults(func=instance_show_command, needs_runtime_context=False)

    instance_remove_parser = instance_subparsers.add_parser(
        "remove",
        help="Remove one instance registration.",
    )
    instance_remove_parser.add_argument("name")
    instance_remove_parser.add_argument("--json", action="store_true")
    instance_remove_parser.set_defaults(func=instance_remove_command, needs_runtime_context=False)

    top_status_parser = subparsers.add_parser(
        "status",
        help="Show daemon, queue, and KB health status.",
    )
    top_status_parser.add_argument("--json", action="store_true")
    top_status_parser.set_defaults(func=status_command, needs_runtime_context=True)
    status_subparsers = top_status_parser.add_subparsers(dest="status_command")

    status_daemon_parser = status_subparsers.add_parser(
        "daemon",
        help="Show daemon lifecycle status.",
    )
    status_daemon_parser.add_argument("--json", action="store_true")
    status_daemon_parser.set_defaults(func=server_status, needs_runtime_context=True)

    status_queue_parser = status_subparsers.add_parser(
        "queue",
        help="Show submission/job/review queue counts.",
    )
    status_queue_parser.add_argument("--json", action="store_true")
    status_queue_parser.set_defaults(func=status_queue_command, needs_runtime_context=True)

    status_health_parser = status_subparsers.add_parser(
        "health",
        help="Show KB health summary and issue counts.",
    )
    status_health_parser.add_argument("--json", action="store_true")
    status_health_parser.set_defaults(func=status_health_command, needs_runtime_context=True)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check whether Sediment and its configured agent backend are healthy.",
    )
    doctor_parser.add_argument(
        "--full",
        action="store_true",
        help="Also run the stricter structured JSON probe used by schema-driven workflows.",
    )
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=doctor_command, needs_runtime_context=True)

    daemon_parser = subparsers.add_parser(
        "__run-platform-daemon",
        help=argparse.SUPPRESS,
    )
    daemon_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    daemon_parser.add_argument("--startup-timeout", type=float, default=10.0)
    daemon_parser.add_argument("--skip-checks", action="store_true")
    daemon_parser.set_defaults(func=run_platform_daemon, needs_runtime_context=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(render_help("overview"))
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "registry", None):
        set_active_registry_path(args.registry)
    if getattr(args, "needs_runtime_context", False):
        try:
            _resolve_cli_context(args)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    elif getattr(args, "config", None):
        set_active_config_path(args.config)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

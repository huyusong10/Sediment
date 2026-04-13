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
from typing import Any

from mcp_server import launcher, worker
from mcp_server.control import (
    apply_review_decision,
    enqueue_tidy_job,
    platform_status_payload,
    resolve_tidy_issue,
)
from mcp_server.instances import (
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
from mcp_server.kb import inventory, resolve_kb_document_path
from mcp_server.llm_cli import (
    build_cli_command,
    collect_output,
    help_command,
    parse_json_object,
    resolve_executable,
)
from mcp_server.platform_services import get_health_payload, list_reviews_with_jobs
from mcp_server.runtime import (
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
    submission_dedupe_window_seconds,
    submission_rate_limit_count,
    submission_rate_limit_window_seconds,
    trust_proxy_headers,
    trusted_proxy_cidrs,
)
from mcp_server.settings import (
    CONFIG_RELATIVE_PATH,
    current_config_path,
    load_settings,
    load_settings_for_path,
    set_active_config_path,
)


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
    from mcp_server import server as server_module

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
            "host": "127.0.0.1",
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
    command = [
        sys.executable,
        "-m",
        "mcp_server.cli",
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
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
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

    if wait_for_health(timeout_seconds=args.startup_timeout):
        print(f"Sediment daemon started (pid={process.pid}).")
        print(f"Portal: {local_health_url().removesuffix('/healthz')}/portal")
        print(f"Admin:  {local_health_url().removesuffix('/healthz')}/admin")
        print(f"Logs:   {paths['log']}")
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
    store = build_store()
    issue = resolve_tidy_issue(
        kb_path=kb_path(),
        target=args.target,
        issue_type=args.issue_type,
    )
    job = enqueue_tidy_job(
        store=store,
        kb_path=kb_path(),
        issue=issue,
        actor_name=args.actor_name or current_actor_name(),
        max_attempts=job_max_attempts(),
    )
    if args.process_once:
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


def build_doctor_payload() -> dict[str, Any]:
    settings = load_settings()
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str, **extra: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, **extra})

    config_path = current_config_path()
    record(
        "config.file",
        bool(settings.get("config_exists")),
        f"Using config file: {config_path}",
        path=str(config_path),
    )

    configured_kb = kb_path()
    record(
        "paths.knowledge_base",
        configured_kb.exists() and configured_kb.is_dir(),
        f"knowledge_base={configured_kb}",
        path=str(configured_kb),
    )

    state_dir = platform_paths()["state_dir"]
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        probe = state_dir / ".doctor-write-check"
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        record("paths.state_dir", True, f"state_dir is writable: {state_dir}", path=str(state_dir))
    except OSError as exc:
        record("paths.state_dir", False, f"state_dir is not writable: {exc}", path=str(state_dir))

    executable = resolve_executable(settings)
    backend = settings["agent"]["backend"]
    record(
        "agent.executable",
        bool(executable),
        (
            f"Resolved backend executable for {backend}: {executable}"
            if executable
            else f"Could not resolve executable for backend {backend}"
        ),
        backend=backend,
        executable=executable,
    )

    if executable:
        try:
            result = subprocess.run(
                help_command(settings),
                cwd=str(project_root()),
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            ok = result.returncode == 0
            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"exit code {result.returncode}"
            )
            record("agent.help", ok, detail, backend=backend)
        except (OSError, subprocess.TimeoutExpired) as exc:
            record("agent.help", False, f"Failed to run help command: {exc}", backend=backend)

        try:
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
                '{"ok": true, "backend": "<backend-name>"} and no extra text.'
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
                result = subprocess.run(
                    invocation.command,
                    input=invocation.stdin_data,
                    cwd=str(temp_root),
                    capture_output=True,
                    text=True,
                    timeout=int(settings["agent"]["doctor_timeout_seconds"]),
                    check=False,
                )
                raw_output = collect_output(
                    invocation,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )
                if result.returncode != 0:
                    detail = raw_output or f"exit code {result.returncode}"
                    record("agent.probe", False, f"Agent probe failed: {detail}", backend=backend)
                else:
                    payload = parse_json_object(raw_output)
                    ok = bool(payload.get("ok")) and str(payload.get("backend", "")).strip()
                    record(
                        "agent.probe",
                        bool(ok),
                        f"Agent probe succeeded for backend {payload.get('backend', backend)}",
                        backend=str(payload.get("backend", backend)),
                    )
        except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            record("agent.probe", False, f"Agent probe failed: {exc}", backend=backend)

    return {
        "status": "ok" if all(item["ok"] for item in checks) else "failed",
        "config_path": str(config_path),
        "instance_name": settings["instance"]["name"],
        "knowledge_name": settings["knowledge"]["name"],
        "backend": backend,
        "checks": checks,
    }


def doctor_command(args) -> int:
    payload = build_doctor_payload()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] == "ok" else 1

    print("Sediment doctor")
    print(f"- config: {payload['config_path']}")
    print(f"- instance: {payload['instance_name']}")
    print(f"- knowledge: {payload['knowledge_name']}")
    print(f"- backend: {payload['backend']}")
    for item in payload["checks"]:
        label = "ok" if item["ok"] else "fail"
        print(f"- [{label}] {item['name']}: {item['detail']}")
    return 0 if payload["status"] == "ok" else 1


def init_command(args) -> int:
    target_root = Path.cwd().resolve()
    config_target = target_root / CONFIG_RELATIVE_PATH

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

    instance_label = args.instance_name or _slugify_instance_name(target_root.name)
    knowledge_label = args.knowledge_name or f"{target_root.name} Knowledge Base"
    existing = get_registered_instance(instance_label)
    if existing is not None:
        existing_config = Path(existing["config_path"]).expanduser().resolve()
        if existing_config != config_target.resolve():
            print(
                f"Instance name '{instance_label}' is already registered at {existing_config}.",
                file=sys.stderr,
            )
            return 1

    backend = args.backend
    if backend == "auto":
        backend = _detect_available_backend()
        if backend is None:
            print(
                "No supported Agent CLI was detected. Install Claude Code CLI, Codex CLI, "
                "or OpenCode CLI, or pass --backend explicitly.",
                file=sys.stderr,
            )
            return 2

    port_value = args.port or _pick_free_port()
    scaffold = _write_instance_scaffold(
        target_root=target_root,
        config_target=config_target,
        instance_label=instance_label,
        knowledge_label=knowledge_label,
        backend=backend,
        port_value=port_value,
        create_kb=not args.no_kb,
    )
    register_instance(
        instance_name=instance_label,
        config_path=config_target,
        knowledge_name=knowledge_label,
    )
    set_active_config_path(config_target)

    doctor = build_doctor_payload()
    payload = {
        "instance_name": instance_label,
        "knowledge_name": knowledge_label,
        "config_path": str(config_target),
        "instance_root": str(target_root),
        "backend": backend,
        "port": port_value,
        "knowledge_base_created": not args.no_kb,
        "registry_path": str(instance_registry_path()),
        "admin_token": scaffold["auth"]["admin_token"],
        "doctor_status": doctor["status"],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if doctor["status"] == "ok" else 1

    print("Sediment instance initialized")
    print(f"- instance: {instance_label}")
    print(f"- knowledge: {knowledge_label}")
    print(f"- root: {target_root}")
    print(f"- config: {config_target}")
    print(f"- backend: {backend}")
    print(f"- port: {port_value}")
    print(f"- registry: {instance_registry_path()}")
    print(f"- admin_token: {scaffold['auth']['admin_token']}")
    print(f"- doctor: {doctor['status']}")
    if doctor["status"] != "ok":
        print("Run `sediment doctor` after fixing the reported issues.", file=sys.stderr)
        return 1
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
        print(
            f"- {item['id']}: {job.get('job_type', '-')} | "
            f"decision={item['decision']} | job={job.get('status', '-')}"
        )
    return 0


def review_show_command(args) -> int:
    store = build_store()
    review = store.get_review(args.review_id)
    if review is None:
        print(f"Review '{args.review_id}' not found.", file=sys.stderr)
        return 1
    job = store.get_job(review["job_id"])
    submission = (
        store.get_submission(review["submission_id"])
        if review.get("submission_id")
        else None
    )
    payload = {"review": review, "job": job, "submission": submission}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"review: {review['id']}")
    print(f"decision: {review['decision']}")
    print(f"job: {job['id']} ({job['job_type']})")
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
                "  sediment init --instance-name ops-prod --knowledge-name \"生产运维知识库\"",
                "  sediment --instance ops-prod doctor",
                "  sediment --instance ops-prod server start",
                "  sediment --instance ops-prod review list",
                "  sediment --instance ops-prod logs follow",
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
                "  sediment help doctor",
            ]
        ),
        "init": "\n".join(
            [
                "sediment init",
                "",
                "Create a Sediment instance in the current directory, write",
                "./config/sediment/config.yaml, register the instance globally, create",
                "a KB scaffold, and run the same health checks used by `sediment doctor`.",
                "",
                "Examples:",
                "  sediment init --instance-name ops-prod --knowledge-name \"生产运维知识库\"",
                "  sediment init --backend codex --port 8123",
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
                "  sediment --instance ops-prod review list",
                "  sediment --instance ops-prod review show <review-id>",
                "  sediment --instance ops-prod review approve <review-id> --reviewer-name alice",
                "  sediment --instance ops-prod review reject <review-id> "
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
                "  sediment --instance ops-prod logs show --lines 80",
                "  sediment --instance ops-prod logs follow --component worker",
            ]
        ),
        "server": "\n".join(
            [
                "sediment server",
                "",
                "Manage the per-instance daemon lifecycle.",
                "",
                "Commands:",
                "  sediment --instance ops-prod server start",
                "  sediment --instance ops-prod server status",
                "  sediment --instance ops-prod server stop",
            ]
        ),
        "kb": "\n".join(
            [
                "sediment kb",
                "",
                "Explore and maintain the formal knowledge layer.",
                "",
                "Commands:",
                "  sediment --instance ops-prod kb list",
                "  sediment --instance ops-prod kb explore \"什么是热备份\"",
                "  sediment --instance ops-prod kb tidy \"薄弱条目\"",
            ]
        ),
        "doctor": "\n".join(
            [
                "sediment doctor",
                "",
                "Check config discovery, KB path, writable state directory, selected Agent CLI,",
                "and a minimal probe prompt against the configured backend.",
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
    parser = argparse.ArgumentParser(description="Unified Sediment control CLI.")
    parser.add_argument(
        "--config",
        help="Path to Sediment config.yaml. Defaults to ./config/sediment/config.yaml.",
    )
    parser.add_argument(
        "--instance",
        help="Use a registered Sediment instance by name.",
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
        choices=["auto", "claude-code", "codex", "opencode"],
        default="auto",
    )
    init_parser.add_argument("--port", type=int)
    init_parser.add_argument("--force", action="store_true")
    init_parser.add_argument("--allow-nested", action="store_true")
    init_parser.add_argument("--no-kb", action="store_true")
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

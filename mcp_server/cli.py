from __future__ import annotations

import argparse
import json
import os
import signal
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
    enqueue_tidy_job,
    platform_status_payload,
    resolve_tidy_issue,
)
from mcp_server.kb import inventory, resolve_kb_document_path
from mcp_server.llm_cli import (
    build_cli_command,
    collect_output,
    help_command,
    parse_json_object,
    resolve_executable,
)
from mcp_server.platform_services import get_health_payload
from mcp_server.runtime import (
    admin_token,
    build_store,
    host,
    job_max_attempts,
    job_stale_after_seconds,
    kb_path,
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
from mcp_server.settings import current_config_path, load_settings, set_active_config_path


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


def doctor_command(args) -> int:
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

    payload = {
        "status": "ok" if all(item["ok"] for item in checks) else "failed",
        "config_path": str(config_path),
        "backend": backend,
        "checks": checks,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["status"] == "ok" else 1

    print("Sediment doctor")
    print(f"- config: {config_path}")
    print(f"- backend: {backend}")
    for item in checks:
        label = "ok" if item["ok"] else "fail"
        print(f"- [{label}] {item['name']}: {item['detail']}")
    return 0 if payload["status"] == "ok" else 1


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
    _apply_config_path_from_argv(argv)
    return launcher.main(argv)


def legacy_server_main(argv: list[str] | None = None) -> int:
    if argv:
        _apply_config_path_from_argv(argv)
    return _server_module().main(argv)


def legacy_worker_main(argv: list[str] | None = None) -> int:
    _apply_config_path_from_argv(argv)
    return worker.main(argv)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified Sediment control CLI.")
    parser.add_argument(
        "--config",
        help="Path to Sediment config.yaml. Defaults to ./config/sediment/config.yaml.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    up_parser = subparsers.add_parser("up", help="Run server + worker in the foreground.")
    up_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    up_parser.add_argument("--startup-timeout", type=float, default=10.0)
    up_parser.add_argument("--skip-checks", action="store_true")
    up_parser.set_defaults(func=server_run)

    server_parser = subparsers.add_parser("server", help="Manage Sediment server/worker processes.")
    server_subparsers = server_parser.add_subparsers(dest="server_command", required=True)

    run_parser = server_subparsers.add_parser("run", help="Run server + worker in the foreground.")
    run_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    run_parser.add_argument("--startup-timeout", type=float, default=10.0)
    run_parser.add_argument("--skip-checks", action="store_true")
    run_parser.set_defaults(func=server_run)

    start_parser = server_subparsers.add_parser("start", help="Start the platform daemon.")
    start_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    start_parser.add_argument("--startup-timeout", type=float, default=10.0)
    start_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    start_parser.add_argument("--skip-checks", action="store_true")
    start_parser.add_argument("--force", action="store_true")
    start_parser.set_defaults(func=start_daemon)

    stop_parser = server_subparsers.add_parser("stop", help="Stop the platform daemon.")
    stop_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    stop_parser.add_argument("--force-kill", action="store_true")
    stop_parser.set_defaults(func=server_stop)

    restart_parser = server_subparsers.add_parser("restart", help="Restart the platform daemon.")
    restart_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    restart_parser.add_argument("--startup-timeout", type=float, default=10.0)
    restart_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    restart_parser.add_argument("--skip-checks", action="store_true")
    restart_parser.set_defaults(func=server_restart)

    status_parser = server_subparsers.add_parser("status", help="Show daemon status.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=server_status)

    logs_parser = server_subparsers.add_parser("logs", help="Show recent daemon logs.")
    logs_parser.add_argument("--lines", type=int, default=60)
    logs_parser.set_defaults(func=server_logs)

    kb_parser = subparsers.add_parser("kb", help="Knowledge-base operations.")
    kb_subparsers = kb_parser.add_subparsers(dest="kb_command", required=True)

    explore_parser = kb_subparsers.add_parser("explore", help="Ask a natural-language KB question.")
    explore_parser.add_argument("question")
    explore_parser.add_argument("--json", action="store_true")
    explore_parser.set_defaults(func=kb_explore)

    health_parser = kb_subparsers.add_parser("health", help="Show KB health summary.")
    health_parser.add_argument("--json", action="store_true")
    health_parser.add_argument("--limit", type=int, default=10)
    health_parser.set_defaults(func=kb_health)

    list_parser = kb_subparsers.add_parser("list", help="List KB entry names.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=kb_list)

    read_parser = kb_subparsers.add_parser("read", help="Read a KB entry.")
    read_parser.add_argument("name")
    read_parser.set_defaults(func=kb_read)

    tidy_parser = kb_subparsers.add_parser("tidy", help="Queue a tidy job for a KB target.")
    tidy_parser.add_argument("target")
    tidy_parser.add_argument("--issue-type")
    tidy_parser.add_argument("--actor-name")
    tidy_parser.add_argument("--process-once", action="store_true")
    tidy_parser.add_argument("--json", action="store_true")
    tidy_parser.set_defaults(func=kb_tidy)

    top_status_parser = subparsers.add_parser(
        "status",
        help="Show daemon, queue, and KB health status.",
    )
    top_status_parser.add_argument("--json", action="store_true")
    top_status_parser.set_defaults(func=status_command)
    status_subparsers = top_status_parser.add_subparsers(dest="status_command")

    status_daemon_parser = status_subparsers.add_parser(
        "daemon",
        help="Show daemon lifecycle status.",
    )
    status_daemon_parser.add_argument("--json", action="store_true")
    status_daemon_parser.set_defaults(func=server_status)

    status_queue_parser = status_subparsers.add_parser(
        "queue",
        help="Show submission/job/review queue counts.",
    )
    status_queue_parser.add_argument("--json", action="store_true")
    status_queue_parser.set_defaults(func=status_queue_command)

    status_health_parser = status_subparsers.add_parser(
        "health",
        help="Show KB health summary and issue counts.",
    )
    status_health_parser.add_argument("--json", action="store_true")
    status_health_parser.set_defaults(func=status_health_command)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check whether Sediment and its configured agent backend are healthy.",
    )
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=doctor_command)

    daemon_parser = subparsers.add_parser(
        "__run-platform-daemon",
        help=argparse.SUPPRESS,
    )
    daemon_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    daemon_parser.add_argument("--startup-timeout", type=float, default=10.0)
    daemon_parser.add_argument("--skip-checks", action="store_true")
    daemon_parser.set_defaults(func=run_platform_daemon)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.config:
        set_active_config_path(args.config)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

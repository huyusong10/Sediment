from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sediment.diagnostics import (
    coerce_log_record,
    emit_log,
    write_log_record,
)
from sediment.llm_cli import resolve_executable
from sediment.quartz_runtime import build_quartz_site, quartz_status
from sediment.runtime import host as runtime_host
from sediment.runtime import instance_root as runtime_instance_root
from sediment.runtime import kb_path as runtime_kb_path
from sediment.runtime import knowledge_name as runtime_knowledge_name
from sediment.runtime import port as runtime_port
from sediment.runtime import platform_paths as runtime_platform_paths
from sediment.runtime import quartz_runtime_dir as runtime_quartz_runtime_dir
from sediment.settings import (
    current_config_path,
    load_settings,
    set_active_config_path,
    source_root,
)

_LOCAL_HTTP_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass
class ProcessSpec:
    name: str
    command: list[str]
    env: dict[str, str] | None = None


@dataclass
class ManagedProcess:
    spec: ProcessSpec
    process: subprocess.Popen[str]
    threads: list[threading.Thread]


def project_root() -> Path:
    return runtime_instance_root()


def default_kb_path() -> Path:
    return runtime_instance_root() / "knowledge-base"


def configured_kb_path() -> Path:
    return runtime_kb_path()


def configured_cli() -> str:
    settings = load_settings()
    return resolve_executable(settings) or ""


def configured_host() -> str:
    return runtime_host()


def configured_port() -> int:
    return runtime_port()


def validate_environment(*, require_cli: bool = True) -> list[str]:
    errors: list[str] = []
    kb_path = configured_kb_path()
    if not kb_path.exists():
        errors.append(
            "Configured knowledge_base path does not exist. "
            f"Expected knowledge base root at: {kb_path}"
        )
    elif not kb_path.is_dir():
        errors.append(f"Configured knowledge_base path is not a directory: {kb_path}")

    if require_cli and not configured_cli():
        errors.append(
            "Configured agent backend executable was not found. "
            "Set agent.backend or agent.command in config/sediment/config.yaml."
        )
    return errors


def build_process_specs(
    *,
    worker_poll_interval: float,
) -> list[ProcessSpec]:
    python = sys.executable
    config_path = str(current_config_path())
    worker_command = [python, "-m", "sediment.worker", "--config", config_path]
    if worker_poll_interval > 0:
        worker_command.extend(["--poll-interval", str(worker_poll_interval)])
    return [
        ProcessSpec(
            name="server",
            command=[
                python,
                "-m",
                "sediment.server",
                "--config",
                config_path,
                "--run-jobs-in-process",
                "false",
            ],
        ),
        ProcessSpec(name="worker", command=worker_command),
    ]


def _forward_output(prefix: str, stream, sink: TextIO) -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            record = coerce_log_record(line.rstrip("\n"), default_component=prefix)
            if not record.get("component"):
                record["component"] = prefix
            if record.get("component") == "unknown":
                record["component"] = prefix
            write_log_record(sink, record)
    finally:
        stream.close()


def spawn_process(spec: ProcessSpec, *, sink: TextIO) -> ManagedProcess:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        f"{source_root()}{os.pathsep}{pythonpath}" if pythonpath else str(source_root())
    )
    if spec.env:
        env.update(spec.env)
    process = subprocess.Popen(
        spec.command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(project_root()),
        env=env,
    )
    threads: list[threading.Thread] = []
    if process.stdout is not None:
        thread = threading.Thread(
            target=_forward_output,
            args=(spec.name, process.stdout, sink),
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    return ManagedProcess(spec=spec, process=process, threads=threads)


def wait_for_server_ready(*, timeout_seconds: float, sink: TextIO) -> bool:
    port = configured_port()
    url = f"http://127.0.0.1:{port}/healthz"
    deadline = time.time() + max(timeout_seconds, 0.2)
    while time.time() < deadline:
        try:
            with _LOCAL_HTTP_OPENER.open(url, timeout=1.5) as response:
                if response.status == 200:
                    emit_log(
                        sink,
                        component="launcher",
                        event="server.ready",
                        message="Server health endpoint is ready.",
                        details={"health_url": url},
                    )
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    emit_log(
        sink,
        component="launcher",
        event="server.ready_timeout",
        message="Timed out waiting for the server health endpoint.",
        level="ERROR",
        details={"health_url": url, "timeout_seconds": timeout_seconds},
    )
    return False


def _terminate_process(process: subprocess.Popen[str], *, timeout_seconds: float) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=max(timeout_seconds, 1.0))


def terminate_all(processes: list[ManagedProcess], *, timeout_seconds: float, sink: TextIO) -> None:
    for managed in processes:
        if managed.process.poll() is None:
            emit_log(
                sink,
                component="launcher",
                event="process.stop_requested",
                message="Stopping managed process.",
                process_name=managed.spec.name,
            )
    for managed in processes:
        _terminate_process(managed.process, timeout_seconds=timeout_seconds)


def _ensure_quartz_site(*, sink: TextIO, force_build: bool) -> bool:
    site_dir = runtime_platform_paths()["state_dir"] / "quartz" / "site"
    runtime_dir = runtime_quartz_runtime_dir()
    status = quartz_status(runtime_dir=runtime_dir, site_dir=site_dir)
    if not force_build:
        if status["runtime_available"] and not status["site_available"]:
            emit_log(
                sink,
                component="launcher",
                event="quartz.site_missing",
                message="Quartz runtime is ready but the site has not been built yet.",
                level="WARNING",
                details={"site_dir": site_dir},
            )
        return True
    try:
        settings = load_settings()
        locale = str(settings.get("locale", "en"))
        emit_log(
            sink,
            component="launcher",
            event="quartz.build_started",
            message="Building Quartz site before startup.",
            details={"site_dir": site_dir, "runtime_dir": runtime_dir},
        )
        build_quartz_site(
            kb_path=configured_kb_path(),
            runtime_dir=runtime_dir,
            site_dir=site_dir,
            knowledge_name=runtime_knowledge_name(),
            locale=locale,
        )
        emit_log(
            sink,
            component="launcher",
            event="quartz.build_completed",
            message="Quartz site is ready.",
            details={"site_dir": site_dir},
        )
        return True
    except RuntimeError as exc:
        emit_log(
            sink,
            component="launcher",
            event="quartz.build_failed",
            message="Quartz site build failed.",
            level="ERROR",
            error=exc,
            details={"site_dir": site_dir},
        )
        return False


def _normalized_exit_code(returncode: int | None) -> int:
    if returncode is None:
        return 1
    return returncode if returncode != 0 else 1


def _wait_for_ready_probe(
    *,
    ready_probe,
    processes: list[ManagedProcess],
    sink: TextIO,
    stop_event: threading.Event,
    shutdown_timeout: float,
) -> int | None:
    outcome: dict[str, object] = {"done": False, "value": False, "error": None}

    def run_probe() -> None:
        try:
            outcome["value"] = bool(ready_probe())
        except Exception as exc:  # noqa: BLE001
            outcome["error"] = exc
        finally:
            outcome["done"] = True

    thread = threading.Thread(target=run_probe, daemon=True)
    thread.start()
    while thread.is_alive():
        exited = [managed for managed in processes if managed.process.poll() is not None]
        if exited:
            first = exited[0]
            emit_log(
                sink,
                component="launcher",
                event="process.startup_exit",
                message=f"{first.spec.name} exited during startup.",
                level="ERROR",
                process_name=first.spec.name,
                details={"returncode": first.process.returncode},
            )
            terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
            return _normalized_exit_code(first.process.returncode)
        if stop_event.is_set():
            terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
            return 0
        thread.join(0.1)
    if outcome["error"] is not None:
        raise outcome["error"]  # type: ignore[misc]
    if not outcome["value"]:
        terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
        return 1
    return None


def run_managed_processes(
    specs: list[ProcessSpec],
    *,
    sink: TextIO | None = None,
    startup_timeout: float = 10.0,
    stop_event: threading.Event | None = None,
    ready_probe=None,
    shutdown_timeout: float = 5.0,
) -> int:
    sink = sink or sys.stdout
    stop_event = stop_event or threading.Event()
    processes: list[ManagedProcess] = []

    try:
        for spec in specs:
            emit_log(
                sink,
                component="launcher",
                event="process.start",
                message=f"Starting {spec.name}.",
                process_name=spec.name,
                details={"command": spec.command},
            )
            managed = spawn_process(spec, sink=sink)
            processes.append(managed)
            time.sleep(0.15)
            if managed.process.poll() is not None:
                emit_log(
                    sink,
                    component="launcher",
                    event="process.startup_exit",
                    message=f"{spec.name} exited during startup.",
                    level="ERROR",
                    process_name=spec.name,
                    details={"returncode": managed.process.returncode},
                )
                return managed.process.returncode or 1

        if ready_probe is not None:
            probe_result = _wait_for_ready_probe(
                ready_probe=ready_probe,
                processes=processes,
                sink=sink,
                stop_event=stop_event,
                shutdown_timeout=shutdown_timeout,
            )
            if probe_result is not None:
                return probe_result

        while not stop_event.is_set():
            exited = [managed for managed in processes if managed.process.poll() is not None]
            if exited:
                first = exited[0]
                emit_log(
                    sink,
                    component="launcher",
                    event="process.exit",
                    message="Managed process exited; stopping remaining services.",
                    level="ERROR",
                    process_name=first.spec.name,
                    details={"returncode": first.process.returncode},
                )
                terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
                return _normalized_exit_code(first.process.returncode)
            time.sleep(0.2)

        terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
        return 0
    finally:
        terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start Sediment server and worker together.",
    )
    parser.add_argument("--config", help=argparse.SUPPRESS)
    parser.add_argument(
        "--worker-poll-interval",
        type=float,
        default=2.0,
        help="Polling interval passed to the worker subprocess.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for the server health endpoint.",
    )
    parser.add_argument(
        "--no-health-check",
        action="store_true",
        help="Skip startup health checks and keep services running in background.",
    )
    parser.add_argument(
        "--build-quartz",
        action="store_true",
        help="Build Quartz site for this instance before launching services.",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip environment validation before starting child services.",
    )
    args = parser.parse_args(argv)
    if args.config:
        set_active_config_path(args.config)

    if not args.skip_checks:
        errors = validate_environment(require_cli=True)
        if errors:
            emit_log(
                sys.stderr,
                component="launcher",
                event="validation.failed",
                message="Cannot start Sediment platform.",
                level="ERROR",
                details={"errors": errors},
            )
            for item in errors:
                emit_log(
                    sys.stderr,
                    component="launcher",
                    event="validation.error",
                    message=item,
                    level="ERROR",
                )
            return 2

    stop_event = threading.Event()

    def handle_signal(signum, _frame) -> None:
        signal_name = signal.Signals(signum).name
        emit_log(
            sys.stdout,
            component="launcher",
            event="signal.received",
            message=f"Received {signal_name}, shutting down.",
            details={"signal": signal_name},
        )
        stop_event.set()

    previous_sigint = signal.signal(signal.SIGINT, handle_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, handle_signal)
    try:
        specs = build_process_specs(
            worker_poll_interval=args.worker_poll_interval,
        )
        emit_log(
            sys.stdout,
            component="launcher",
            event="startup.banner",
            message="Sediment platform launcher starting.",
            details={
                "kb_path": configured_kb_path(),
                "port": configured_port(),
                "portal_url": f"http://127.0.0.1:{configured_port()}/",
                "admin_url": f"http://127.0.0.1:{configured_port()}/admin/overview",
                "health_url": f"http://127.0.0.1:{configured_port()}/healthz",
            },
        )
        if not _ensure_quartz_site(sink=sys.stdout, force_build=args.build_quartz):
            return 1
        if args.no_health_check:
            emit_log(
                sys.stdout,
                component="launcher",
                event="startup.health_check_skipped",
                message="Startup health check is disabled (--no-health-check).",
            )
        return run_managed_processes(
            specs,
            sink=sys.stdout,
            startup_timeout=args.startup_timeout,
            stop_event=stop_event,
            ready_probe=(
                None
                if args.no_health_check
                else lambda: wait_for_server_ready(
                    timeout_seconds=args.startup_timeout,
                    sink=sys.stdout,
                )
            ),
        )
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())

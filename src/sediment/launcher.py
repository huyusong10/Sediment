from __future__ import annotations

import argparse
import os
import secrets
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
    startup_admin_token: str | None = None,
) -> list[ProcessSpec]:
    python = sys.executable
    config_path = str(current_config_path())
    startup_admin_token = (startup_admin_token or "").strip() or secrets.token_urlsafe(18)
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
            env={"SEDIMENT_STARTUP_ADMIN_TOKEN": startup_admin_token},
        ),
        ProcessSpec(name="worker", command=worker_command),
    ]


def _forward_output(prefix: str, stream, sink: TextIO) -> None:
    try:
        for line in iter(stream.readline, ""):
            if not line:
                break
            _write_log_line(sink, prefix, line.rstrip("\n"))
    finally:
        stream.close()


def _write_log_line(sink: TextIO, prefix: str, message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    sink.write(f"{timestamp} [{prefix}] {message}\n")
    sink.flush()


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
                    _write_log_line(sink, "up", f"Server ready at {url}")
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    _write_log_line(sink, "up", f"Timed out waiting for server health endpoint: {url}")
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
            _write_log_line(sink, "up", f"Stopping {managed.spec.name}...")
    for managed in processes:
        _terminate_process(managed.process, timeout_seconds=timeout_seconds)


def _ensure_quartz_site(*, sink: TextIO, force_build: bool) -> bool:
    site_dir = runtime_platform_paths()["state_dir"] / "quartz" / "site"
    runtime_dir = runtime_quartz_runtime_dir()
    status = quartz_status(runtime_dir=runtime_dir, site_dir=site_dir)
    if not force_build:
        if status["runtime_available"] and not status["site_available"]:
            _write_log_line(
                sink,
                "up",
                "Quartz runtime is ready but site is not built yet. "
                "Run `sediment server start --build-quartz --no-health-check` to build it.",
            )
        return True
    try:
        settings = load_settings()
        locale = str(settings.get("locale", "en"))
        _write_log_line(sink, "up", "Building Quartz site before startup (--build-quartz)...")
        build_quartz_site(
            kb_path=configured_kb_path(),
            runtime_dir=runtime_dir,
            site_dir=site_dir,
            knowledge_name=runtime_knowledge_name(),
            locale=locale,
        )
        _write_log_line(sink, "up", f"Quartz site is ready: {site_dir}")
        return True
    except RuntimeError as exc:
        _write_log_line(sink, "up", f"Quartz build failed: {exc}")
        return False


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
            _write_log_line(sink, "up", f"Starting {spec.name}: {' '.join(spec.command)}")
            managed = spawn_process(spec, sink=sink)
            processes.append(managed)
            time.sleep(0.15)
            if managed.process.poll() is not None:
                _write_log_line(
                    sink,
                    "up",
                    f"{spec.name} exited during startup with code {managed.process.returncode}",
                )
                return managed.process.returncode or 1

        if ready_probe is not None and not ready_probe():
            terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
            return 1

        while not stop_event.is_set():
            exited = [managed for managed in processes if managed.process.poll() is not None]
            if exited:
                first = exited[0]
                _write_log_line(
                    sink,
                    "up",
                    f"{first.spec.name} exited with code {first.process.returncode}; "
                    "stopping remaining services.",
                )
                terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
                return first.process.returncode or 0
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
            print("[up] Cannot start Sediment platform:", file=sys.stderr)
            for item in errors:
                print(f"[up] - {item}", file=sys.stderr)
            return 2

    stop_event = threading.Event()

    def handle_signal(signum, _frame) -> None:
        signal_name = signal.Signals(signum).name
        _write_log_line(sys.stdout, "up", f"Received {signal_name}, shutting down...")
        stop_event.set()

    previous_sigint = signal.signal(signal.SIGINT, handle_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, handle_signal)
    try:
        startup_admin_token = os.environ.get("SEDIMENT_STARTUP_ADMIN_TOKEN", "").strip()
        if not startup_admin_token:
            startup_admin_token = secrets.token_urlsafe(18)
        specs = build_process_specs(
            worker_poll_interval=args.worker_poll_interval,
            startup_admin_token=startup_admin_token,
        )
        _write_log_line(sys.stdout, "up", "Sediment platform launcher")
        _write_log_line(sys.stdout, "up", f"KB path:  {configured_kb_path()}")
        _write_log_line(sys.stdout, "up", f"Port:     {configured_port()}")
        _write_log_line(sys.stdout, "up", f"Portal:   http://127.0.0.1:{configured_port()}/portal")
        _write_log_line(sys.stdout, "up", f"Admin:    http://127.0.0.1:{configured_port()}/admin")
        _write_log_line(sys.stdout, "up", f"Health:   http://127.0.0.1:{configured_port()}/healthz")
        _write_log_line(sys.stdout, "up", f"Admin token: {startup_admin_token}")
        if not _ensure_quartz_site(sink=sys.stdout, force_build=args.build_quartz):
            return 1
        if args.no_health_check:
            _write_log_line(
                sys.stdout,
                "up",
                "Startup health check is disabled (--no-health-check).",
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

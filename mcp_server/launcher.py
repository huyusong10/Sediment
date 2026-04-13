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

from mcp_server.llm_cli import resolve_executable
from mcp_server.runtime import host as runtime_host
from mcp_server.runtime import kb_path as runtime_kb_path
from mcp_server.runtime import port as runtime_port
from mcp_server.runtime import project_root as runtime_project_root
from mcp_server.settings import current_config_path, load_settings, set_active_config_path


@dataclass
class ProcessSpec:
    name: str
    command: list[str]


@dataclass
class ManagedProcess:
    spec: ProcessSpec
    process: subprocess.Popen[str]
    threads: list[threading.Thread]


def project_root() -> Path:
    return runtime_project_root()


def default_kb_path() -> Path:
    return runtime_project_root() / "knowledge-base"


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


def build_process_specs(*, worker_poll_interval: float) -> list[ProcessSpec]:
    python = sys.executable
    config_path = str(current_config_path())
    worker_command = [python, "-m", "mcp_server.worker", "--config", config_path]
    if worker_poll_interval > 0:
        worker_command.extend(["--poll-interval", str(worker_poll_interval)])
    return [
        ProcessSpec(
            name="server",
            command=[
                python,
                "-m",
                "mcp_server.server",
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
            sink.write(f"[{prefix}] {line}")
            sink.flush()
    finally:
        stream.close()


def spawn_process(spec: ProcessSpec, *, sink: TextIO) -> ManagedProcess:
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
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
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status == 200:
                    sink.write(f"[up] Server ready at {url}\n")
                    sink.flush()
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    sink.write(f"[up] Timed out waiting for server health endpoint: {url}\n")
    sink.flush()
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
            sink.write(f"[up] Stopping {managed.spec.name}...\n")
            sink.flush()
    for managed in processes:
        _terminate_process(managed.process, timeout_seconds=timeout_seconds)


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
            sink.write(f"[up] Starting {spec.name}: {' '.join(spec.command)}\n")
            sink.flush()
            managed = spawn_process(spec, sink=sink)
            processes.append(managed)
            time.sleep(0.15)
            if managed.process.poll() is not None:
                sink.write(
                    f"[up] {spec.name} exited during startup "
                    f"with code {managed.process.returncode}\n"
                )
                sink.flush()
                return managed.process.returncode or 1

        if ready_probe is not None and not ready_probe():
            terminate_all(processes, timeout_seconds=shutdown_timeout, sink=sink)
            return 1

        while not stop_event.is_set():
            exited = [managed for managed in processes if managed.process.poll() is not None]
            if exited:
                first = exited[0]
                sink.write(
                    f"[up] {first.spec.name} exited with code {first.process.returncode}; "
                    "stopping remaining services.\n"
                )
                sink.flush()
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
        print(f"[up] Received {signal_name}, shutting down...")
        stop_event.set()

    previous_sigint = signal.signal(signal.SIGINT, handle_signal)
    previous_sigterm = signal.signal(signal.SIGTERM, handle_signal)
    try:
        specs = build_process_specs(worker_poll_interval=args.worker_poll_interval)
        print("[up] Sediment platform launcher")
        print(f"[up] KB path:  {configured_kb_path()}")
        print(f"[up] Port:     {configured_port()}")
        print(f"[up] Portal:   http://127.0.0.1:{configured_port()}/portal")
        print(f"[up] Admin:    http://127.0.0.1:{configured_port()}/admin")
        print(f"[up] Health:   http://127.0.0.1:{configured_port()}/healthz")
        return run_managed_processes(
            specs,
            sink=sys.stdout,
            startup_timeout=args.startup_timeout,
            stop_event=stop_event,
            ready_probe=lambda: wait_for_server_ready(
                timeout_seconds=args.startup_timeout,
                sink=sys.stdout,
            ),
        )
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())

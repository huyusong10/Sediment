from __future__ import annotations

import argparse
import socket
import time
from pathlib import Path

from sediment.diagnostics import DiagnosticLogger
from sediment.platform_store import PlatformStore
from sediment.runtime import (
    build_agent_runner,
    job_stale_after_seconds,
)
from sediment.runtime import (
    build_store as runtime_build_store,
)
from sediment.runtime import (
    kb_path as runtime_kb_path,
)
from sediment.runtime import (
    platform_paths as runtime_platform_paths,
)
from sediment.runtime import (
    project_root as runtime_project_root,
)
from sediment.settings import set_active_config_path

LOGGER = DiagnosticLogger("worker")


def project_root() -> Path:
    return runtime_project_root()


def kb_path() -> Path:
    return runtime_kb_path()


def platform_paths() -> dict[str, Path]:
    return runtime_platform_paths()


def build_store():
    return runtime_build_store()


def build_runner(store: PlatformStore):
    return build_agent_runner(store=store)


def process_next_job(*, store: PlatformStore | None = None, runner=None) -> bool:
    store = store or build_store()
    runner = runner or build_runner(store)
    job = store.claim_next_job(
        runner_host=socket.gethostname(),
        stale_after_seconds=job_stale_after_seconds(),
    )
    if job is None:
        return False
    LOGGER.info(
        "job.claimed",
        "Worker claimed a job.",
        job_id=job["id"],
        details={
            "job_type": job["job_type"],
            "attempt_count": job.get("attempt_count"),
        },
    )
    runner.run_job_now(job["id"])
    return True


def process_queue_until_idle(*, max_jobs: int | None = None) -> int:
    store = build_store()
    runner = build_runner(store)
    processed = 0
    while True:
        if max_jobs is not None and processed >= max_jobs:
            break
        if not process_next_job(store=store, runner=runner):
            break
        processed += 1
    return processed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Sediment background worker.")
    parser.add_argument("--config", help=argparse.SUPPRESS)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process queued jobs once and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds to sleep between queue polls in daemon mode.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Optional maximum number of jobs to process before exit.",
    )
    args = parser.parse_args(argv)
    if args.config:
        set_active_config_path(args.config)

    if args.once:
        processed = process_queue_until_idle(max_jobs=args.max_jobs)
        LOGGER.info(
            "worker.once.completed",
            "Sediment worker processed queued jobs once.",
            details={"processed_jobs": processed, "max_jobs": args.max_jobs},
        )
        return 0

    store = build_store()
    runner = build_runner(store)
    processed = 0
    LOGGER.info(
        "worker.started",
        "Sediment worker started.",
        details={
            "kb_path": kb_path(),
            "db_path": platform_paths()["db_path"],
            "hostname": socket.gethostname(),
            "poll_interval_seconds": max(args.poll_interval, 0.2),
            "max_jobs": args.max_jobs,
        },
    )
    while True:
        if args.max_jobs is not None and processed >= args.max_jobs:
            break
        did_work = process_next_job(store=store, runner=runner)
        if did_work:
            processed += 1
            continue
        time.sleep(max(args.poll_interval, 0.2))
    LOGGER.info(
        "worker.stopped",
        "Sediment worker exiting.",
        details={"processed_jobs": processed},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

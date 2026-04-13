from __future__ import annotations

import argparse
import socket
import time
from pathlib import Path

from mcp_server.platform_store import PlatformStore
from mcp_server.runtime import (
    build_agent_runner,
    job_stale_after_seconds,
)
from mcp_server.runtime import (
    build_store as runtime_build_store,
)
from mcp_server.runtime import (
    kb_path as runtime_kb_path,
)
from mcp_server.runtime import (
    platform_paths as runtime_platform_paths,
)
from mcp_server.runtime import (
    project_root as runtime_project_root,
)
from mcp_server.settings import set_active_config_path


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
        print(f"Sediment worker processed {processed} job(s).")
        return 0

    store = build_store()
    runner = build_runner(store)
    processed = 0
    print("Sediment worker started.")
    print(f"KB path:    {kb_path()}")
    print(f"DB path:    {platform_paths()['db_path']}")
    print(f"Hostname:   {socket.gethostname()}")
    while True:
        if args.max_jobs is not None and processed >= args.max_jobs:
            break
        did_work = process_next_job(store=store, runner=runner)
        if did_work:
            processed += 1
            continue
        time.sleep(max(args.poll_interval, 0.2))
    print(f"Sediment worker exiting after processing {processed} job(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import socket
import time
from pathlib import Path

from mcp_server.agent_runner import get_agent_runner
from mcp_server.platform_services import ensure_platform_state
from mcp_server.platform_store import PlatformStore


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def kb_path() -> Path:
    raw = str(project_root() / "knowledge-base")
    return Path(os.environ.get("SEDIMENT_KB_PATH", raw))


def platform_paths() -> dict[str, Path]:
    state_dir = Path(os.environ.get("SEDIMENT_STATE_DIR", str(project_root() / ".sediment_state")))
    return {
        "state_dir": state_dir,
        "db_path": Path(os.environ.get("SEDIMENT_DB_PATH", str(state_dir / "platform.db"))),
        "uploads_dir": Path(os.environ.get("SEDIMENT_UPLOADS_DIR", str(state_dir / "uploads"))),
        "workspaces_dir": Path(
            os.environ.get("SEDIMENT_WORKSPACES_DIR", str(state_dir / "workspaces"))
        ),
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
    return store


def build_runner(store: PlatformStore):
    return get_agent_runner(
        project_root=project_root(),
        kb_path=kb_path(),
        workspaces_dir=platform_paths()["workspaces_dir"],
        store=store,
    )


def process_next_job(*, store: PlatformStore | None = None, runner=None) -> bool:
    store = store or build_store()
    runner = runner or build_runner(store)
    job = store.claim_next_job(
        runner_host=socket.gethostname(),
        stale_after_seconds=env_int("SEDIMENT_JOB_STALE_AFTER_SECONDS", 900, minimum=0),
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

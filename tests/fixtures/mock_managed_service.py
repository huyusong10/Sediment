from __future__ import annotations

import os
import signal
import sys
import time


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    name = argv[0] if argv else "service"
    fail_fast = os.environ.get(f"MOCK_{name.upper()}_FAIL_FAST", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    run_seconds = float(os.environ.get("MOCK_SERVICE_RUN_SECONDS", "30"))
    stop = False

    def handle_signal(_signum, _frame) -> None:
        nonlocal stop
        stop = True
        print(f"{name} stopping", flush=True)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print(f"{name} ready", flush=True)
    if fail_fast:
        return 3

    deadline = time.time() + run_seconds
    while not stop and time.time() < deadline:
        print(f"{name} heartbeat", flush=True)
        time.sleep(0.2)

    print(f"{name} exit", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

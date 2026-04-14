from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import Any


def build_cli_parser(handlers: Mapping[str, Any]) -> argparse.ArgumentParser:
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
    init_parser.set_defaults(func=handlers["init_command"], needs_runtime_context=False)

    help_parser = subparsers.add_parser("help", help="Show Sediment task-oriented help.")
    help_parser.add_argument("topic", nargs="?")
    help_parser.set_defaults(func=handlers["cli_help_command"], needs_runtime_context=False)

    server_parser = subparsers.add_parser("server", help="Manage Sediment server/worker processes.")
    server_subparsers = server_parser.add_subparsers(dest="server_command", required=True)

    run_parser = server_subparsers.add_parser("run", help="Run server + worker in the foreground.")
    run_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    run_parser.add_argument("--startup-timeout", type=float, default=10.0)
    run_parser.add_argument("--no-health-check", action="store_true")
    run_parser.add_argument("--build-quartz", action="store_true")
    run_parser.add_argument("--skip-checks", action="store_true")
    run_parser.set_defaults(func=handlers["server_run"], needs_runtime_context=True)

    start_parser = server_subparsers.add_parser("start", help="Start the platform daemon.")
    start_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    start_parser.add_argument("--startup-timeout", type=float, default=10.0)
    start_parser.add_argument("--no-health-check", action="store_true")
    start_parser.add_argument("--build-quartz", action="store_true")
    start_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    start_parser.add_argument("--skip-checks", action="store_true")
    start_parser.add_argument("--force", action="store_true")
    start_parser.set_defaults(func=handlers["start_daemon"], needs_runtime_context=True)

    stop_parser = server_subparsers.add_parser("stop", help="Stop the platform daemon.")
    stop_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    stop_parser.add_argument("--force-kill", action="store_true")
    stop_parser.set_defaults(func=handlers["server_stop"], needs_runtime_context=True)

    restart_parser = server_subparsers.add_parser("restart", help="Restart the platform daemon.")
    restart_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    restart_parser.add_argument("--startup-timeout", type=float, default=10.0)
    restart_parser.add_argument("--no-health-check", action="store_true")
    restart_parser.add_argument("--build-quartz", action="store_true")
    restart_parser.add_argument("--shutdown-timeout", type=float, default=8.0)
    restart_parser.add_argument("--skip-checks", action="store_true")
    restart_parser.set_defaults(func=handlers["server_restart"], needs_runtime_context=True)

    status_parser = server_subparsers.add_parser("status", help="Show daemon status.")
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=handlers["server_status"], needs_runtime_context=True)

    kb_parser = subparsers.add_parser("kb", help="Knowledge-base operations.")
    kb_subparsers = kb_parser.add_subparsers(dest="kb_command", required=True)

    explore_parser = kb_subparsers.add_parser("explore", help="Ask a natural-language KB question.")
    explore_parser.add_argument("question")
    explore_parser.add_argument("--json", action="store_true")
    explore_parser.set_defaults(func=handlers["kb_explore"], needs_runtime_context=True)

    health_parser = kb_subparsers.add_parser("health", help="Show KB health summary.")
    health_parser.add_argument("--json", action="store_true")
    health_parser.add_argument("--limit", type=int, default=10)
    health_parser.set_defaults(func=handlers["kb_health"], needs_runtime_context=True)

    list_parser = kb_subparsers.add_parser("list", help="List KB entry names.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=handlers["kb_list"], needs_runtime_context=True)

    read_parser = kb_subparsers.add_parser("read", help="Read a KB entry.")
    read_parser.add_argument("name")
    read_parser.set_defaults(func=handlers["kb_read"], needs_runtime_context=True)

    tidy_parser = kb_subparsers.add_parser("tidy", help="Queue a tidy job for a KB target.")
    tidy_parser.add_argument("target")
    tidy_parser.add_argument("--issue-type")
    tidy_parser.add_argument("--actor-name")
    tidy_parser.add_argument("--process-once", action="store_true")
    tidy_parser.add_argument("--json", action="store_true")
    tidy_parser.set_defaults(func=handlers["kb_tidy"], needs_runtime_context=True)

    review_parser = subparsers.add_parser("review", help="Inspect and resolve pending reviews.")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)

    review_list_parser = review_subparsers.add_parser("list", help="List reviews.")
    review_list_parser.add_argument("--decision", default="pending")
    review_list_parser.add_argument("--limit", type=int, default=20)
    review_list_parser.add_argument("--json", action="store_true")
    review_list_parser.set_defaults(
        func=handlers["review_list_command"],
        needs_runtime_context=True,
    )

    review_show_parser = review_subparsers.add_parser("show", help="Show one review.")
    review_show_parser.add_argument("review_id")
    review_show_parser.add_argument("--json", action="store_true")
    review_show_parser.set_defaults(
        func=handlers["review_show_command"],
        needs_runtime_context=True,
    )

    review_approve_parser = review_subparsers.add_parser("approve", help="Approve a review.")
    review_approve_parser.add_argument("review_id")
    review_approve_parser.add_argument("--reviewer-name")
    review_approve_parser.add_argument("--comment", default="")
    review_approve_parser.add_argument("--json", action="store_true")
    review_approve_parser.set_defaults(
        func=handlers["review_approve_command"],
        needs_runtime_context=True,
    )

    review_reject_parser = review_subparsers.add_parser("reject", help="Reject a review.")
    review_reject_parser.add_argument("review_id")
    review_reject_parser.add_argument("--reviewer-name")
    review_reject_parser.add_argument("--comment", default="")
    review_reject_parser.add_argument("--json", action="store_true")
    review_reject_parser.set_defaults(
        func=handlers["review_reject_command"],
        needs_runtime_context=True,
    )

    top_logs_parser = subparsers.add_parser(
        "logs",
        help="Read daemon logs for the current instance.",
    )
    top_logs_subparsers = top_logs_parser.add_subparsers(dest="logs_command", required=True)

    logs_show_parser = top_logs_subparsers.add_parser("show", help="Show recent log lines.")
    logs_show_parser.add_argument(
        "--component",
        choices=["all", "server", "worker", "up"],
        default="all",
    )
    logs_show_parser.add_argument("--lines", type=int, default=60)
    logs_show_parser.set_defaults(func=handlers["logs_show_command"], needs_runtime_context=True)

    logs_follow_parser = top_logs_subparsers.add_parser("follow", help="Follow daemon logs.")
    logs_follow_parser.add_argument(
        "--component",
        choices=["all", "server", "worker", "up"],
        default="all",
    )
    logs_follow_parser.add_argument("--lines", type=int, default=30)
    logs_follow_parser.set_defaults(
        func=handlers["logs_follow_command"],
        needs_runtime_context=True,
    )

    quartz_parser = subparsers.add_parser(
        "quartz",
        help="Manage Quartz graph site for the current instance.",
    )
    quartz_subparsers = quartz_parser.add_subparsers(dest="quartz_command", required=True)

    quartz_status_parser = quartz_subparsers.add_parser("status", help="Show Quartz runtime/site status.")
    quartz_status_parser.add_argument(
        "--build-if-missing",
        action="store_true",
        help="Automatically build the site when runtime is ready but site is missing.",
    )
    quartz_status_parser.add_argument("--timeout-seconds", type=int, default=240)
    quartz_status_parser.add_argument("--json", action="store_true")
    quartz_status_parser.set_defaults(
        func=handlers["quartz_status_command"],
        needs_runtime_context=True,
    )

    quartz_build_parser = quartz_subparsers.add_parser("build", help="Build or refresh Quartz site.")
    quartz_build_parser.add_argument("--timeout-seconds", type=int, default=240)
    quartz_build_parser.add_argument("--json", action="store_true")
    quartz_build_parser.set_defaults(
        func=handlers["quartz_build_command"],
        needs_runtime_context=True,
    )

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
    submit_text_parser.set_defaults(
        func=handlers["submit_text_command"],
        needs_runtime_context=True,
    )

    submit_file_parser = submit_subparsers.add_parser(
        "file",
        help="Submit a document file, folder, or zip archive.",
    )
    submit_file_parser.add_argument("path")
    submit_file_parser.add_argument("--filename")
    submit_file_parser.add_argument("--mime-type")
    submit_file_parser.add_argument("--name", dest="submitter_name")
    submit_file_parser.add_argument("--json", action="store_true")
    submit_file_parser.set_defaults(
        func=handlers["submit_file_command"],
        needs_runtime_context=True,
    )

    instance_parser = subparsers.add_parser(
        "instance",
        help="Manage registered Sediment instances.",
    )
    instance_subparsers = instance_parser.add_subparsers(dest="instance_command", required=True)

    instance_list_parser = instance_subparsers.add_parser("list", help="List known instances.")
    instance_list_parser.add_argument("--json", action="store_true")
    instance_list_parser.set_defaults(
        func=handlers["instance_list_command"],
        needs_runtime_context=False,
    )

    instance_show_parser = instance_subparsers.add_parser("show", help="Show one instance.")
    instance_show_parser.add_argument("name")
    instance_show_parser.add_argument("--json", action="store_true")
    instance_show_parser.set_defaults(
        func=handlers["instance_show_command"],
        needs_runtime_context=False,
    )

    instance_remove_parser = instance_subparsers.add_parser(
        "remove",
        help="Remove one instance registration.",
    )
    instance_remove_parser.add_argument("name")
    instance_remove_parser.add_argument(
        "--delete-files",
        action="store_true",
        help="Also delete the instance root directory after unregistering.",
    )
    instance_remove_parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=8.0,
        help="Seconds to wait when stopping the instance daemon before deletion.",
    )
    instance_remove_parser.add_argument("--json", action="store_true")
    instance_remove_parser.set_defaults(
        func=handlers["instance_remove_command"],
        needs_runtime_context=False,
    )

    instance_unlock_parser = instance_subparsers.add_parser(
        "unlock",
        help="Stop daemon/clear stale locks so instance files can be removed safely.",
    )
    instance_unlock_parser.add_argument("name", nargs="?")
    instance_unlock_parser.add_argument(
        "--path",
        help="Instance root directory or config/sediment/config.yaml path (works even if unregistered).",
    )
    instance_unlock_parser.add_argument(
        "--all-deleted",
        action="store_true",
        help="Unlock all unregistered instances found under --search-root.",
    )
    instance_unlock_parser.add_argument(
        "--all",
        action="store_true",
        help="Unlock all discovered instances (registered + unregistered) under --search-root.",
    )
    instance_unlock_parser.add_argument(
        "--search-root",
        default=".",
        help="Root directory used by --all-deleted to discover leftover instance folders.",
    )
    instance_unlock_parser.add_argument(
        "--shutdown-timeout",
        type=float,
        default=8.0,
        help="Seconds to wait for graceful daemon shutdown before returning.",
    )
    instance_unlock_parser.add_argument(
        "--force-kill",
        action="store_true",
        help="Escalate to SIGKILL when graceful shutdown times out.",
    )
    instance_unlock_parser.add_argument("--json", action="store_true")
    instance_unlock_parser.set_defaults(
        func=handlers["instance_unlock_command"],
        needs_runtime_context=False,
    )

    top_status_parser = subparsers.add_parser(
        "status",
        help="Show overall platform status, or focus on queue / KB health.",
    )
    top_status_parser.add_argument("--json", action="store_true")
    top_status_parser.set_defaults(func=handlers["status_command"], needs_runtime_context=True)
    status_subparsers = top_status_parser.add_subparsers(dest="status_command")

    status_queue_parser = status_subparsers.add_parser(
        "queue",
        help="Show submission/job/review queue counts.",
    )
    status_queue_parser.add_argument("--json", action="store_true")
    status_queue_parser.set_defaults(
        func=handlers["status_queue_command"],
        needs_runtime_context=True,
    )

    status_health_parser = status_subparsers.add_parser(
        "health",
        help="Show KB health summary and issue counts.",
    )
    status_health_parser.add_argument("--json", action="store_true")
    status_health_parser.set_defaults(
        func=handlers["status_health_command"],
        needs_runtime_context=True,
    )

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
    doctor_parser.set_defaults(func=handlers["doctor_command"], needs_runtime_context=True)

    daemon_parser = subparsers.add_parser(
        "__run-platform-daemon",
        help=argparse.SUPPRESS,
    )
    daemon_parser.add_argument("--worker-poll-interval", type=float, default=2.0)
    daemon_parser.add_argument("--startup-timeout", type=float, default=10.0)
    daemon_parser.add_argument("--no-health-check", action="store_true")
    daemon_parser.add_argument("--build-quartz", action="store_true")
    daemon_parser.add_argument("--skip-checks", action="store_true")
    daemon_parser.set_defaults(func=handlers["run_platform_daemon"], needs_runtime_context=True)

    return parser

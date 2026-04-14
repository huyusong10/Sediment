from __future__ import annotations


def render_help(topic: str | None) -> str:
    topic = (topic or "overview").strip().lower()
    topics = {
        "overview": "\n".join(
            [
                "Sediment help",
                "",
                "Core workflow:",
                "  sediment init",
                "  sediment instance list",
                "  sediment doctor",
                "  sediment server start",
                "  sediment kb explore \"什么是热备份\"",
                "  sediment submit text --title \"新概念\" --content \"...\"",
                "  sediment submit file ./reports --name alice",
                "  sediment review list",
                "  sediment logs follow",
                "",
                "Anywhere management:",
                "  sediment --instance ops-prod doctor",
                "  sediment --instance ops-prod server start",
                "  sediment --instance ops-prod review list",
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
                "  sediment help submit",
                "  sediment help doctor",
            ]
        ),
        "init": "\n".join(
            [
                "sediment init",
                "",
                "Create a Sediment instance in the current directory.",
                "",
                "In a normal terminal, `sediment init` opens an interactive setup wizard.",
                "Press Enter to keep defaults, or pass --no-interactive for scripts and CI.",
                "If you work inside the instance root or its knowledge-base directory,",
                "Sediment resolves the local config automatically and you usually do not need",
                "`--instance`.",
                "",
                "Examples:",
                "  sediment init",
                "  sediment init --instance-name ops-prod --knowledge-name \"生产运维知识库\"",
                "  sediment init --backend codex --host 0.0.0.0 --port 8123 --no-interactive",
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
                "  sediment review list",
                "  sediment review show <review-id>",
                "  sediment review approve <review-id> --reviewer-name alice",
                "  sediment review reject <review-id> --comment \"needs more evidence\"",
            ]
        ),
        "logs": "\n".join(
            [
                "sediment logs",
                "",
                "Read daemon logs for the current instance. Use --component all|server|worker|up.",
                "",
                "Commands:",
                "  sediment logs show --lines 80",
                "  sediment logs follow --component worker",
            ]
        ),
        "server": "\n".join(
            [
                "sediment server",
                "",
                "Manage the per-instance daemon lifecycle.",
                "Server startup relies on configured owner / committer users in config.",
                "",
                "Commands:",
                "  sediment server start",
                "  sediment server run",
                "  sediment server status",
                "  sediment server stop",
            ]
        ),
        "kb": "\n".join(
            [
                "sediment kb",
                "",
                "Explore and maintain the formal knowledge layer.",
                "",
                "Commands:",
                "  sediment kb list",
                "  sediment kb explore \"什么是热备份\"",
                "  sediment kb tidy --scope graph --reason \"repair dangling links\"",
            ]
        ),
        "user": "\n".join(
            [
                "sediment user",
                "",
                "Manage configured owner / committer identities for the admin console.",
                "",
                "Commands:",
                "  sediment user list",
                "  sediment user create --name \"Ops Committer\"",
                "  sediment user show-token owner",
                "  sediment user disable user-1234",
            ]
        ),
        "doctor": "\n".join(
            [
                "sediment doctor",
                "",
                "Run a layered health check for the current Sediment instance.",
                "",
                "Quick mode checks config discovery, paths, port availability, executable",
                "resolution, CLI help, and a simple generation probe.",
                "",
                "Use `sediment doctor --full` to also run the stricter structured JSON probe",
                "used by tidy and other schema-driven workflows.",
            ]
        ),
        "submit": "\n".join(
            [
                "sediment submit",
                "",
                "Create buffered submissions from the CLI using the same backend logic",
                "as the Web portal and MCP tools.",
                "",
                "Commands:",
                "  sediment submit text --title \"新概念\" --content \"...\" --type concept",
                "  sediment submit text --title \"来自 stdin\" --type feedback < note.txt",
                "  sediment submit file ./incident.docx --name alice",
                "  sediment submit file ./incident-bundle.zip --name alice",
                "  sediment submit file ./reports-folder --name alice",
            ]
        ),
    }
    return topics.get(topic, topics["overview"])

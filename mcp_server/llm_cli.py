from __future__ import annotations

import json
import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(slots=True)
class AgentCliInvocation:
    backend: str
    command: list[str]
    stdin_data: str | None
    output_file: Path | None = None


def build_cli_command(
    settings: dict[str, Any],
    prompt: str,
    *,
    prompt_file: Path | None = None,
    payload_file: Path | None = None,
    skill_file: Path | None = None,
    extra_args: Iterable[str] | None = None,
    cwd: Path | None = None,
) -> AgentCliInvocation:
    agent = settings["agent"]
    backend = str(agent["backend"])
    prefix = _command_prefix(agent)
    args = list(extra_args or [])

    if backend == "claude-code":
        command = [*prefix, "-p"]
        if agent.get("model"):
            command.extend(["--model", str(agent["model"])])
        if agent.get("reasoning_effort"):
            command.extend(["--effort", str(agent["reasoning_effort"])])
        if agent.get("permission_mode"):
            command.extend(["--permission-mode", str(agent["permission_mode"])])
        if agent.get("dangerously_skip_permissions"):
            command.append("--dangerously-skip-permissions")
        command.extend(_extra_args(agent))
        command.extend(args)
        command.extend(["--", prompt])
        return AgentCliInvocation(backend=backend, command=command, stdin_data=None)

    if backend == "codex":
        if prompt_file is None:
            raise RuntimeError("Codex backend requires a prompt file context.")
        output_file = prompt_file.parent / "codex-last-message.txt"
        command = [*prefix, "exec"]
        if agent.get("model"):
            command.extend(["-m", str(agent["model"])])
        if agent.get("profile"):
            command.extend(["-p", str(agent["profile"])])
        if agent.get("sandbox"):
            command.extend(["--sandbox", str(agent["sandbox"])])
        command.append("--skip-git-repo-check")
        command.extend(["--output-last-message", str(output_file)])
        command.extend(_extra_args(agent))
        command.append("-")
        return AgentCliInvocation(
            backend=backend,
            command=command,
            stdin_data=prompt,
            output_file=output_file,
        )

    if backend == "opencode":
        command = [*prefix, "run"]
        if cwd is not None:
            command.extend(["--dir", str(cwd)])
        command.extend(["--format", "default"])
        if agent.get("model"):
            command.extend(["-m", str(agent["model"])])
        if agent.get("variant"):
            command.extend(["--variant", str(agent["variant"])])
        if agent.get("agent_name"):
            command.extend(["--agent", str(agent["agent_name"])])
        if agent.get("dangerously_skip_permissions"):
            command.append("--dangerously-skip-permissions")
        command.extend(_extra_args(agent))
        command.append(prompt)
        return AgentCliInvocation(backend=backend, command=command, stdin_data=None)

    raise RuntimeError(f"Unsupported Sediment agent backend: {backend}")


def collect_output(
    invocation: AgentCliInvocation,
    *,
    stdout: str,
    stderr: str,
) -> str:
    if invocation.output_file is not None and invocation.output_file.exists():
        file_output = invocation.output_file.read_text(encoding="utf-8").strip()
        if file_output:
            return file_output
    return stdout.strip() or stderr.strip()


def help_command(settings: dict[str, Any]) -> list[str]:
    agent = settings["agent"]
    prefix = _command_prefix(agent)
    backend = str(agent["backend"])
    if backend == "codex":
        return [*prefix, "exec", "--help"]
    if backend == "opencode":
        return [*prefix, "run", "--help"]
    return [*prefix, "--help"]


def resolve_executable(settings: dict[str, Any]) -> str | None:
    prefix = _command_prefix(settings["agent"])
    executable = prefix[0]
    if Path(executable).is_absolute():
        return executable if Path(executable).exists() else None
    return shutil.which(executable)


def parse_json_object(raw_output: str) -> dict[str, Any]:
    candidates = [raw_output.strip()]
    start = raw_output.find("{")
    end = raw_output.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw_output[start : end + 1].strip())

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("Agent CLI did not return a JSON object.")


def _command_prefix(agent_settings: dict[str, Any]) -> list[str]:
    configured = agent_settings.get("command")
    if isinstance(configured, list):
        command = [str(item) for item in configured if str(item).strip()]
    elif configured:
        command = shlex.split(str(configured), posix=os.name != "nt")
    else:
        command = [_default_executable(str(agent_settings["backend"]))]
    if not command:
        raise RuntimeError("Agent CLI command resolved to an empty executable.")
    return command


def _default_executable(backend: str) -> str:
    if backend == "claude-code":
        return "claude"
    if backend == "codex":
        return "codex"
    if backend == "opencode":
        return "opencode"
    raise RuntimeError(f"Unsupported Sediment agent backend: {backend}")


def _extra_args(agent_settings: dict[str, Any]) -> list[str]:
    value = agent_settings.get("extra_args") or []
    return [str(item) for item in value]

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Iterable

_PLACEHOLDER_TOKENS = ("{prompt}", "{prompt_file}", "{payload_file}", "{skill_file}")


def build_cli_command(
    cli_value: str,
    prompt: str,
    *,
    prompt_file: Path | None = None,
    payload_file: Path | None = None,
    skill_file: Path | None = None,
    extra_args: Iterable[str] | None = None,
) -> tuple[list[str], str | None]:
    """Build a prompt-execution command from a configurable CLI string.

    The contract is intentionally small:
    - a CLI string may contain placeholders such as ``{prompt}``
    - bare ``claude`` commands get ``-p ... -- <prompt>`` appended automatically
    - any other command receives the prompt via stdin
    """
    cli_value = cli_value.strip()
    if not cli_value:
        raise RuntimeError("CLI command is empty.")

    if any(token in cli_value for token in _PLACEHOLDER_TOKENS):
        command = shlex.split(
            cli_value.format(
                prompt=prompt,
                prompt_file=str(prompt_file or ""),
                payload_file=str(payload_file or ""),
                skill_file=str(skill_file or ""),
            )
        )
        if not command:
            raise RuntimeError("CLI command did not resolve to an executable.")
        return command, None

    command = shlex.split(cli_value)
    if not command:
        raise RuntimeError("CLI command did not resolve to an executable.")

    executable = Path(command[0]).name.lower()
    if executable == "claude":
        command = [*command, "-p", *(extra_args or []), "--", prompt]
        return command, None

    return command, prompt

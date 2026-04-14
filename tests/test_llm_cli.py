from __future__ import annotations

from pathlib import Path

from sediment.llm_cli import build_cli_command


def test_codex_reasoning_effort_is_forwarded_to_cli(tmp_path: Path) -> None:
    settings = {
        "agent": {
            "backend": "codex",
            "command": "codex",
            "model": None,
            "profile": None,
            "reasoning_effort": "medium",
            "sandbox": "workspace-write",
            "permission_mode": None,
            "variant": None,
            "agent_name": None,
            "dangerously_skip_permissions": False,
            "extra_args": [],
        }
    }

    invocation = build_cli_command(
        settings,
        "test prompt",
        prompt_file=tmp_path / "prompt.txt",
        cwd=tmp_path,
    )

    assert invocation.backend == "codex"
    assert "-c" in invocation.command
    assert 'model_reasoning_effort="medium"' in invocation.command

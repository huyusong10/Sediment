from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

from mcp_server import retrieval, server


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def _build_project(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

    _write(
        project_root / "skills" / "explore.md",
        """
        ---
        name: test-explore
        runtime_contract:
          shortlist_limit: 4
          neighbor_depth: 1
          max_context_entries: 6
          max_snippets_per_entry: 2
          snippet_char_limit: 240
          cli_timeout_seconds: 30
        ---

        EXPLORE-RUNTIME-MARKER

        Return JSON only.
        """,
    )

    _write(
        kb_path / "entries" / "热备份.md",
        """
        ---
        aliases: [热切换]
        status: formal
        ---
        # 热备份

        热备份是在切换前准备好[[金蝉脱壳]]和[[回音壁]]的接管能力。

        ## Context
        适用于需要连续服务且必须缩短恢复时间的系统，在主备或双活架构中尤为常见。

        ## Why This Matters
        它让故障恢复从临时抢修变成受控切换，避免在事故期间再创建新的风险点。

        ## Common Pitfalls
        常见误区是只准备数据副本，却没有验证[[金蝉脱壳]]与[[回音壁]]的协同接管链路。

        ## Related
        - [[金蝉脱壳]] - 切换策略
        - [[回音壁]] - 观测同步

        ## Source
        - backup_design.md
        """,
    )

    return project_root, kb_path


def test_knowledge_ask_uses_explore_skill_and_cli(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_project(tmp_path)
    cli_path = Path(__file__).parent / "fixtures" / "mock_explore_cli.py"

    monkeypatch.setenv("SEDIMENT_CLI", f"{sys.executable} {cli_path}")
    monkeypatch.setenv("MOCK_REQUIRED_MARKER", "EXPLORE-RUNTIME-MARKER")
    monkeypatch.setattr(server, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(server, "KB_PATH", kb_path)

    raw = asyncio.run(server._knowledge_ask("什么是热备份？"))
    payload = json.loads(raw)

    assert payload["sources"] == ["热备份"]
    assert payload["confidence"] == "high"
    assert payload["exploration_summary"]["mode"] == "definition-driven"
    assert "热备份" in payload["answer"]


def test_answer_question_does_not_fall_back_to_materials(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    kb_path = project_root / "knowledge-base"

    _write(
        project_root / "skills" / "explore.md",
        """
        ---
        name: test-explore
        ---

        Explore skill body.
        """,
    )
    _write(
        project_root / "testcase" / "material" / "secret.md",
        """
        # 外部秘密

        外部秘密是一个只存在于原始材料里的概念。
        """,
    )

    result = retrieval.answer_question("什么是外部秘密？", kb_path, project_root)
    assert result["sources"] == []
    assert result["confidence"] == "low"
    assert "no formal entries" in result["answer"].lower()


def test_answer_question_returns_explicit_error_when_cli_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_root, kb_path = _build_project(tmp_path)

    monkeypatch.setenv("SEDIMENT_CLI", "definitely-not-a-real-cli")
    result = retrieval.answer_question("什么是热备份？", kb_path, project_root)

    assert result["sources"] == []
    assert result["confidence"] == "low"
    assert "unavailable" in result["error"].lower()

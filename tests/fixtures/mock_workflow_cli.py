from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _read_prompt(argv: list[str]) -> str:
    if "exec" in argv and "-" in argv:
        return sys.stdin.read()
    if "-p" in argv:
        if "--" in argv:
            return " ".join(argv[argv.index("--") + 1 :])
        prompt_index = argv.index("-p") + 1
        if prompt_index < len(argv):
            return argv[prompt_index]
    if "run" in argv:
        filtered = argv[:]
        if "--format" in filtered:
            format_index = filtered.index("--format")
            del filtered[format_index : format_index + 2]
        if "--dir" in filtered:
            dir_index = filtered.index("--dir")
            del filtered[dir_index : dir_index + 2]
        if len(filtered) > 1:
            return " ".join(filtered[1:]) if filtered[0] == "run" else " ".join(filtered)
    return sys.stdin.read()


def _write_output(argv: list[str], text: str) -> None:
    if "--output-last-message" in argv:
        output_index = argv.index("--output-last-message") + 1
        if output_index < len(argv):
            Path(argv[output_index]).write_text(text, encoding="utf-8")
            print('{"event":"done"}')
            return
    print(text)


def main() -> int:
    argv = sys.argv[1:]
    if "--help" in argv:
        print("mock workflow cli help")
        return 0

    prompt = _read_prompt(argv.copy())
    if "internal Sediment explore runtime" in prompt:
        if os.environ.get("MOCK_EXPLORE_INVALID_JSON", "").strip().lower() in {"1", "true", "yes", "on"}:
            _write_output(argv, "not-json-response")
            return 0
        if os.environ.get("MOCK_EXPLORE_STRUCTURED_SUMMARY", "").strip().lower() in {"1", "true", "yes", "on"}:
            _write_output(
                argv,
                (
                    "The response has been provided as a structured JSON object via the "
                    "StructuredOutput tool. The answer synthesizes the backup definition from multiple KB entries:\n"
                    "- **Prepared capability**: 热备份是在故障切换前准备好的可接管能力。\n"
                    "- **Key sources**: 热备份, 回音壁\n"
                    "- **Confidence**: high — because the KB contains direct formal definitions for the concept and its supporting operational context."
                ),
            )
            return 0
        if os.environ.get("MOCK_EXPLORE_LEAKED_ANSWER", "").strip().lower() in {"1", "true", "yes", "on"}:
            payload = {
                "answer": prompt,
                "sources": ["热备份", "回音壁"],
                "confidence": "high",
                "exploration_summary": {
                    "entries_scanned": 2,
                    "entries_read": 2,
                    "links_followed": 1,
                    "mode": "definition-driven",
                },
                "gaps": [],
                "contradictions": [],
            }
            _write_output(argv, json.dumps(payload, ensure_ascii=False))
            return 0
        payload = {
            "answer": "热备份是在故障切换前准备好的可接管能力。",
            "sources": ["热备份", "回音壁"],
            "confidence": "high",
            "exploration_summary": {
                "entries_scanned": 2,
                "entries_read": 2,
                "links_followed": 1,
                "mode": "definition-driven",
            },
            "gaps": [],
            "contradictions": [],
        }
    elif "Sediment ingest runner." in prompt:
        payload = {
            "summary": "Generated one conservative ingest draft.",
            "warnings": [],
            "drafts": [
                {
                    "name": "热备份提交草案",
                    "entry_type": "concept",
                    "rationale": "Submission contains a reusable operations concept.",
                    "content": """---
type: concept
status: inferred
aliases: []
sources:
  - portal submission
---
# 热备份提交草案

热备份提交草案是从门户文本提交中提炼出的保守概念草案。

## Scope
适用于首次沉淀新概念且证据仍然有限的企业知识提交流程。

## Related
- [[热备份]] - 已存在的相关概念
""",
                }
            ],
        }
    elif "Sediment tidy runner." in prompt:
        payload = {
            "summary": "Tidy updated one weak entry.",
            "warnings": [],
            "changes": [
                {
                    "name": "薄弱条目",
                    "change_type": "update",
                    "rationale": "Fill missing Scope and strengthen Related links.",
                    "content": """---
type: concept
status: fact
aliases: []
sources:
  - weak_note.md
---
# 薄弱条目

薄弱条目是需要补全结构后才能稳定服务检索与问答的概念条目。

## Scope
适用于结构不足、摘要过短或关联关系过弱的知识条目治理场景。

## Related
- [[暗流]] - 相关概念
- [[回音壁]] - 可补充上下文
""",
                }
            ],
        }
    elif "Sediment submission triage assistant." in prompt:
        payload = {
            "summary": (
                "The submission overlaps with existing backup knowledge "
                "and looks safe to ingest conservatively."
            ),
            "recommended_title": "热备份浏览器提案",
            "recommended_type": "concept",
            "duplicate_risk": "medium",
            "committer_action": "ingest",
            "committer_note": "Link it to 热备份 and 回音壁 before promoting it to a fact.",
            "related_entries": [
                {"name": "热备份", "reason": "Existing concept with adjacent scope."},
                {"name": "回音壁", "reason": "Provides operational context for backup decisions."},
            ],
        }
    else:
        payload = {"ok": True, "backend": "mock"}
    _write_output(argv, json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

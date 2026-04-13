from __future__ import annotations

import json
import sys


def main() -> int:
    prompt = sys.stdin.read()
    if "Sediment ingest runner." in prompt:
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
    else:
        payload = {"summary": "Unknown prompt", "warnings": ["no-op"], "drafts": []}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

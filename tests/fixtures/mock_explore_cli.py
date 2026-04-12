from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    prompt = sys.stdin.read()
    prompt_file = os.environ.get("SEDIMENT_EXPLORE_PROMPT_FILE")
    if not prompt and prompt_file:
        prompt = Path(prompt_file).read_text(encoding="utf-8")

    required_marker = os.environ.get("MOCK_REQUIRED_MARKER")
    if required_marker and required_marker not in prompt:
        print(f"missing required marker: {required_marker}", file=sys.stderr)
        return 3

    payload_file = os.environ.get("SEDIMENT_EXPLORE_PAYLOAD_FILE")
    payload = {}
    if payload_file:
        payload = json.loads(Path(payload_file).read_text(encoding="utf-8"))

    context = payload.get("context", {})
    candidates = context.get("expanded_candidates", [])
    snippets = context.get("candidate_snippets", {})
    formal_names = [item["name"] for item in candidates if item.get("kind") == "formal"]

    if formal_names:
        primary = formal_names[0]
        summary = snippets.get(primary, {}).get("summary", "")
        answer = f"{primary}：{summary or 'mock explore answer'}"
        sources = [primary]
    else:
        answer = "No formal evidence found."
        sources = []

    result = {
        "answer": answer,
        "sources": sources,
        "confidence": "high" if sources else "low",
        "exploration_summary": {
            "entries_scanned": context.get("inventory_overview", {}).get("formal_entry_count", 0),
            "entries_read": len(formal_names[:2]),
            "links_followed": max(len(candidates) - len(formal_names[:1]), 0),
            "mode": "definition-driven",
        },
        "gaps": [] if sources else ["No formal evidence found."],
        "contradictions": [],
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

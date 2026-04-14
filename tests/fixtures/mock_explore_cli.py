from __future__ import annotations

import json
import os
import re
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
    if "run" in argv and len(argv) > 1:
        filtered = argv[:]
        if "--format" in filtered:
            format_index = filtered.index("--format")
            del filtered[format_index : format_index + 2]
        if "--dir" in filtered:
            dir_index = filtered.index("--dir")
            del filtered[dir_index : dir_index + 2]
        return " ".join(filtered[1:]) if filtered and filtered[0] == "run" else " ".join(filtered)
    return sys.stdin.read()


def main() -> int:
    argv = sys.argv[1:]
    if "--help" in argv:
        print("mock explore cli help")
        return 0

    prompt = _read_prompt(argv)
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
    elif "## Prepared Context" in prompt:
        match = re.search(r"## Prepared Context\s*(\{.*\})\s*$", prompt, re.DOTALL)
        if match:
            payload = json.loads(match.group(1))

    context = payload.get("prepared_context", payload.get("context", {}))
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
    if "--output-last-message" in argv:
        output_index = argv.index("--output-last-message") + 1
        if output_index < len(argv):
            Path(argv[output_index]).write_text(
                json.dumps(result, ensure_ascii=False),
                encoding="utf-8",
            )
            print('{"event":"done"}')
            return 0
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

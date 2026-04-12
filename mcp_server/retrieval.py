from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

from scripts.kb_query import inventory, prepare_explore_context, validate_answer

DEFAULT_CONTRACT = {
    "shortlist_limit": 8,
    "neighbor_depth": 2,
    "max_context_entries": 12,
    "max_snippets_per_entry": 2,
    "snippet_char_limit": 320,
    "cli_timeout_seconds": 90,
}


def answer_question(question: str, kb_path: Path, project_root: Path) -> dict[str, Any]:
    question = question.strip()
    if not question:
        return _error_payload("Question must not be empty.")

    skill_path = project_root / "skills" / "explore.md"
    if not skill_path.exists():
        return _error_payload(f"Explore skill not found: {skill_path}")

    inventory_data = inventory(kb_path)
    if not inventory_data["entries"]:
        return {
            "answer": (
                "Knowledge base has no formal entries yet, so explore cannot answer reliably."
            ),
            "sources": [],
            "confidence": "low",
            "exploration_summary": {
                "entries_scanned": 0,
                "entries_read": 0,
                "links_followed": 0,
                "mode": "no-evidence",
            },
            "gaps": ["No formal entries are available in the knowledge base."],
            "contradictions": [],
        }

    try:
        skill_body, runtime_contract = _load_explore_skill(skill_path)
        context = prepare_explore_context(
            question,
            inventory_data=inventory_data,
            shortlist_limit=runtime_contract["shortlist_limit"],
            neighbor_depth=runtime_contract["neighbor_depth"],
            max_context_entries=runtime_contract["max_context_entries"],
            max_snippets_per_entry=runtime_contract["max_snippets_per_entry"],
            snippet_char_limit=runtime_contract["snippet_char_limit"],
        )

        if not context["expanded_candidates"]:
            return {
                "answer": (
                    "No sufficiently relevant knowledge entries were found for this question."
                ),
                "sources": [],
                "confidence": "low",
                "exploration_summary": {
                    "entries_scanned": len(inventory_data["entries"]),
                    "entries_read": 0,
                    "links_followed": 0,
                    "mode": "no-match",
                },
                "gaps": [
                    "The current KB does not expose an obvious formal entry for this question."
                ],
                "contradictions": [],
            }

        prompt = _build_explore_prompt(question, skill_body, runtime_contract, context)
        raw_output = _run_explore_cli(
            prompt=prompt,
            project_root=project_root,
            skill_path=skill_path,
            payload={
                "question": question,
                "runtime_contract": runtime_contract,
                "context": context,
            },
            timeout_seconds=runtime_contract["cli_timeout_seconds"],
        )
        parsed_output = _parse_cli_json(raw_output)
        validation = validate_answer(parsed_output, inventory_data=inventory_data)
        if not validation["valid"]:
            details = "; ".join(validation["errors"])
            return _error_payload(f"Explore runtime returned invalid JSON: {details}")

        return validation["normalized"]
    except RuntimeError as exc:
        return _error_payload(str(exc))


def _load_explore_skill(skill_path: Path) -> tuple[str, dict[str, Any]]:
    content = skill_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)
    runtime_contract = dict(DEFAULT_CONTRACT)
    extra_contract = frontmatter.get("runtime_contract") or {}
    if isinstance(extra_contract, dict):
        runtime_contract.update(
            {
                key: value
                for key, value in extra_contract.items()
                if key in DEFAULT_CONTRACT and isinstance(value, type(DEFAULT_CONTRACT[key]))
            }
        )
    return body.strip(), runtime_contract


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if not match:
        return {}, text
    frontmatter = yaml.safe_load(match.group(1)) or {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, text[match.end() :]


def _build_explore_prompt(
    question: str,
    skill_body: str,
    runtime_contract: dict[str, Any],
    context: dict[str, Any],
) -> str:
    payload = {
        "question": question,
        "runtime_contract": runtime_contract,
        "prepared_context": context,
    }

    return "\n\n".join(
        [
            "You are the internal Sediment explore runtime.",
            "Use only the prepared KB context in this prompt. Do not read raw materials. "
            "Do not invent sources. Placeholder entries are weak evidence and must not be the "
            "only basis of an answer.",
            "Return JSON only. No prose before or after the JSON object.",
            skill_body,
            "## Prepared Context",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _run_explore_cli(
    *,
    prompt: str,
    project_root: Path,
    skill_path: Path,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> str:
    cli_value = os.environ.get("SEDIMENT_CLI", "claude").strip()
    if not cli_value:
        raise RuntimeError("SEDIMENT_CLI is empty; configure a CLI for explore runtime.")

    with tempfile.TemporaryDirectory(prefix="sediment-explore-") as temp_dir:
        temp_root = Path(temp_dir)
        prompt_file = temp_root / "prompt.txt"
        payload_file = temp_root / "payload.json"
        prompt_file.write_text(prompt, encoding="utf-8")
        payload_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        env = os.environ.copy()
        env.update(
            {
                "SEDIMENT_EXPLORE_PROMPT_FILE": str(prompt_file),
                "SEDIMENT_EXPLORE_PAYLOAD_FILE": str(payload_file),
                "SEDIMENT_EXPLORE_SKILL_FILE": str(skill_path),
            }
        )

        command, stdin_data = _build_cli_command(
            cli_value=cli_value,
            prompt=prompt,
            prompt_file=prompt_file,
            payload_file=payload_file,
            skill_file=skill_path,
        )
        try:
            result = subprocess.run(
                command,
                input=stdin_data,
                text=True,
                capture_output=True,
                cwd=str(project_root),
                env=env,
                timeout=timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Explore runtime CLI is unavailable: {exc.filename or cli_value}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Explore runtime timed out after {timeout_seconds} seconds."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            detail = stderr or stdout or f"exit code {result.returncode}"
            raise RuntimeError(f"Explore runtime CLI failed: {detail}")

        output = result.stdout.strip() or result.stderr.strip()
        if not output:
            raise RuntimeError("Explore runtime CLI returned no output.")
        return output


def _build_cli_command(
    *,
    cli_value: str,
    prompt: str,
    prompt_file: Path,
    payload_file: Path,
    skill_file: Path,
) -> tuple[list[str], str | None]:
    placeholders = ("{prompt}", "{prompt_file}", "{payload_file}", "{skill_file}")
    if any(token in cli_value for token in placeholders):
        command = shlex.split(
            cli_value.format(
                prompt=prompt,
                prompt_file=str(prompt_file),
                payload_file=str(payload_file),
                skill_file=str(skill_file),
            )
        )
        return command, None

    command = shlex.split(cli_value)
    if not command:
        raise RuntimeError("SEDIMENT_CLI did not resolve to a command.")

    executable = Path(command[0]).name.lower()
    if executable == "claude":
        return [*command, "-p", "--", prompt], None

    return command, prompt


def _parse_cli_json(raw_output: str) -> dict[str, Any]:
    candidates = [raw_output.strip()]

    fenced = re.search(r"```json\s*(\{.*?\})\s*```", raw_output, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    start = raw_output.find("{")
    end = raw_output.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw_output[start : end + 1].strip())

    seen = set()
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

    raise RuntimeError("Explore runtime did not return a valid JSON object.")


def _error_payload(message: str) -> dict[str, Any]:
    return {
        "answer": message,
        "sources": [],
        "confidence": "low",
        "exploration_summary": {
            "entries_scanned": 0,
            "entries_read": 0,
            "links_followed": 0,
            "mode": "error",
        },
        "gaps": [message],
        "contradictions": [],
        "error": message,
    }

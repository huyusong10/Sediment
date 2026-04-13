#!/usr/bin/env python3
"""
health_check.py — Sediment Knowledge Base diagnostic report.

Usage:
    python skills/health/scripts/health_check.py <kb_path>
    python skills/health/scripts/health_check.py <kb_path> --json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Allow running from the repo root:
# python skills/health/scripts/health_check.py knowledge-base
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from mcp_server.kb import audit_kb, count_placeholder_refs


def run_health_check(kb_path: str) -> dict:
    root = Path(kb_path)
    if not root.is_dir():
        raise FileNotFoundError(f"{kb_path!r} is not a directory.")

    report = audit_kb(kb_path)
    placeholder_refs = count_placeholder_refs(kb_path)
    report["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report["placeholder_ref_buckets"] = {
        "high": sum(1 for item in placeholder_refs if item["ref_count"] >= 5),
        "medium": sum(1 for item in placeholder_refs if 2 <= item["ref_count"] <= 4),
        "low": sum(1 for item in placeholder_refs if item["ref_count"] == 1),
    }
    return report


def print_report(report: dict) -> None:
    print("Sediment Knowledge Base — Health Report")
    print("========================================")
    print(f"Generated: {report['generated_at']}")
    print()
    print("SUMMARY")
    print("-------")
    print(
        f"Formal entries:      {report['formal_entry_count']}  "
        f"(concepts: {report['concept_entry_count']}, lessons: {report['lesson_entry_count']})"
    )
    print(f"Placeholders:        {report['placeholder_count']}")
    print(
        f"Entry size:          avg={report['avg_entry_size']}  "
        f"p50={report['p50_entry_size']}  p90={report['p90_entry_size']}"
    )
    print()
    print("STRUCTURE QUALITY")
    print("-----------------")
    print(f"Hard-fail entries:   {report['hard_fail_entry_count']}")
    print(f"Bad placeholders:    {report['invalid_placeholder_count']}")
    print(f"Missing Scope:       {report['missing_scope_count']}")
    print(f"Missing Trigger:     {report['missing_trigger_count']}")
    print(f"Missing Why:         {report['missing_why_count']}")
    print(f"Missing Risks:       {report['missing_risks_count']}")
    print(f"Weak Related:        {report['weak_related_count']}")
    if report["top_shallow_entries"]:
        print("Top broken entries:")
        for item in report["top_shallow_entries"][:5]:
            joined = "; ".join(item["hard_failures"][:3])
            print(f"  - {item['name']}: {joined}")
    print()
    print("GRAPH HEALTH")
    print("------------")
    print(f"Dangling links:      {report['dangling_link_count']}")
    print(f"Orphan entries:      {report['orphan_entry_count']}")
    print(f"Provenance noise:    {report['provenance_contamination_count']}")
    print(
        "Placeholder refs:    "
        f"high={report['placeholder_ref_buckets']['high']}  "
        f"medium={report['placeholder_ref_buckets']['medium']}  "
        f"low={report['placeholder_ref_buckets']['low']}"
    )
    print()
    print("INDEX HEALTH")
    print("------------")
    print(f"Indexes:             {report['index_count']}")
    print(f"Root index present:  {report['root_index_present']}")
    print(f"Overloaded indexes:  {report['overloaded_index_count']}")
    print(f"Unknown index links: {report['unknown_index_link_count']}")
    print(f"Uncovered entries:   {report['uncovered_formal_entry_count']}")
    if report["overloaded_indexes"]:
        for item in report["overloaded_indexes"][:5]:
            print(
                f"  - {item['name']} (entries={item['entry_count']}, "
                f"tokens={item['estimated_tokens']})"
            )
    print()
    print("CONCEPT COVERAGE")
    print("----------------")
    print(f"Promotable placeholders: {report['promotable_placeholder_count']}")
    if report["promotable_placeholders"]:
        for item in report["promotable_placeholders"][:5]:
            print(f"  - {item['name']} ({item['ref_count']} refs)")
    print(f"Concept gaps:            {report['canonical_gap_count']}")
    if report["canonical_gaps"]:
        for item in report["canonical_gaps"][:5]:
            refs = ", ".join(item["referenced_by"][:3])
            print(f"  - {item['name']} <- {refs}")
    print()
    print("RECOMMENDATION")
    print("--------------")
    for line in build_recommendations(report):
        print(line)


def build_recommendations(report: dict) -> list[str]:
    recommendations = []
    if report["hard_fail_entry_count"]:
        recommendations.append(
            f"Run tidy to repair {report['hard_fail_entry_count']} structurally invalid entries."
        )
    if report["promotable_placeholder_count"]:
        recommendations.append(
            "Run tidy with inductive reasoning to promote high-reference placeholders."
        )
    if report["canonical_gap_count"]:
        recommendations.append(
            "Run tidy concept coverage pass; "
            f"{report['canonical_gap_count']} placeholders are referenced by formal entries."
        )
    if report["dangling_link_count"] or report["orphan_entry_count"]:
        recommendations.append(
            "Run tidy graph repair to resolve dangling links and orphan entries."
        )
    if report["provenance_contamination_count"]:
        recommendations.append(
            "Clean provenance-only wikilinks so sources stay metadata instead of graph edges."
        )
    if report["overloaded_index_count"]:
        recommendations.append(
            "Run tidy index refactor: split or merge oversized index segments."
        )
    if report["unknown_index_link_count"]:
        recommendations.append("Repair broken index links to keep index routing reliable.")
    if report["uncovered_formal_entry_count"]:
        recommendations.append(
            "Expand index coverage so formal entries can be reached from index navigation."
        )
    if not recommendations:
        recommendations.append("Knowledge base looks healthy. Continue ingesting documents.")
    return recommendations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "Usage: python skills/health/scripts/health_check.py <kb_path> [--json]",
            file=sys.stderr,
        )
        return 1

    as_json = False
    if "--json" in args:
        as_json = True
        args.remove("--json")

    if len(args) != 1:
        print(
            "Usage: python skills/health/scripts/health_check.py <kb_path> [--json]",
            file=sys.stderr,
        )
        return 1

    kb_path = args[0]
    try:
        report = run_health_check(kb_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

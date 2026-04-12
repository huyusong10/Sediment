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

from skills.explore.scripts.kb_query import audit_kb
from skills.tidy.scripts.tidy_utils import count_placeholder_refs


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
        f"(placeholders: {report['placeholder_count']})"
    )
    print(
        f"Entry size:          avg={report['avg_entry_size']}  "
        f"p50={report['p50_entry_size']}  p90={report['p90_entry_size']}"
    )
    print()
    print("CONTENT QUALITY")
    print("---------------")
    print(f"Hard-fail entries:   {report['hard_fail_entry_count']}")
    print(f"Missing Why:         {report['missing_why_count']}")
    print(f"Missing Pitfalls:    {report['missing_common_pitfalls_count']}")
    print(f"Weak inline links:   {report['weak_inline_link_count']}")
    if report["top_shallow_entries"]:
        print("Top shallow entries:")
        for item in report["top_shallow_entries"][:5]:
            joined = "; ".join(item["hard_failures"][:3])
            print(f"  - {item['name']}: {joined}")
    print()
    print("GRAPH HEALTH")
    print("------------")
    print(f"Dangling links:      {report['dangling_link_count']}")
    print(f"Orphan entries:      {report['orphan_entry_count']}")
    print(
        "Placeholder refs:    "
        f"high={report['placeholder_ref_buckets']['high']}  "
        f"medium={report['placeholder_ref_buckets']['medium']}  "
        f"low={report['placeholder_ref_buckets']['low']}"
    )
    print()
    print("CANONICALIZATION")
    print("----------------")
    print(f"Promotable placeholders: {report['promotable_placeholder_count']}")
    if report["promotable_placeholders"]:
        for item in report["promotable_placeholders"][:5]:
            print(f"  - {item['name']} ({item['ref_count']} refs)")
    print(f"Canonical gaps:          {report['canonical_gap_count']}")
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
            f"Run tidy to repair {report['hard_fail_entry_count']} hard-fail entries."
        )
    if report["promotable_placeholder_count"]:
        recommendations.append(
            "Run tidy with inductive reasoning to promote high-reference placeholders."
        )
    if report["canonical_gap_count"]:
        recommendations.append(
            "Run tidy canonicalization; "
            f"{report['canonical_gap_count']} concepts need formal entries."
        )
    if report["dangling_link_count"] or report["orphan_entry_count"]:
        recommendations.append(
            "Run tidy graph repair to resolve dangling links and orphan entries."
        )
    if not recommendations:
        recommendations.append("Knowledge base looks healthy. Continue ingesting documents.")
    return recommendations


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python skills/health/scripts/health_check.py <kb_path> [--json]", file=sys.stderr)
        return 1

    as_json = False
    if "--json" in args:
        as_json = True
        args.remove("--json")

    if len(args) != 1:
        print("Usage: python skills/health/scripts/health_check.py <kb_path> [--json]", file=sys.stderr)
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

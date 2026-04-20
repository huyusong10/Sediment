from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sediment.insights import (
    build_cluster_key,
    detect_query_language,
    fingerprint_actor,
    normalize_query_for_kb,
)
from sediment.kb import inventory
from sediment.platform_services import (
    emit_explore_graph_events,
    ensure_platform_state,
    infer_mime_type,
    list_insight_proposals,
    submit_feedback_item,
    submit_uploaded_document_item,
)
from sediment.platform_store import PlatformStore
from sediment.settings import load_settings_for_path

SEED_CLUSTER_SPECS = (
    {
        "intent": "workflow",
        "normalized_subject": "启明回退窗口",
        "insight_id": "insight-qiming-rollback-window",
        "source_entries": ["启明", "试音", "静默态", "锁龙井", "晨祷"],
        "answer_excerpt": "启明失败后要先停注、切回静默态，再由锁龙井与晨祷完成回退确认。",
        "queries": [
            ("启明失败后应该怎么回退？", "portal", "night-watch"),
            ("什么时候需要在晨祷前完成启明回退确认？", "admin_explore", "ops-lead"),
            ("锁龙井和静默态在启明回退里怎么配合？", "portal", "day-watch"),
        ],
    },
    {
        "intent": "risk",
        "normalized_subject": "灰羽名单",
        "insight_id": "insight-grey-feather-watchlist",
        "source_entries": ["守望者", "看门狗", "巡河", "晦暗", "溢彩"],
        "answer_excerpt": "连续弱异常但未越线的对象应进入灰羽名单，由守望者与巡河持续追踪。",
        "queries": [
            ("什么情况下要把谐振腔加入灰羽名单？", "admin_explore", "night-watch"),
            ("看门狗和守望者怎么协同维护灰羽名单？", "portal", "ops-lead"),
            ("晦暗但还没到红线时应该怎么处理？", "admin_explore", "quality-audit"),
        ],
    },
    {
        "intent": "relation",
        "normalized_subject": "旁路画像",
        "insight_id": "insight-bypass-profile-mapping",
        "source_entries": ["照妖镜", "溯光", "回音壁", "幽灵读数"],
        "answer_excerpt": "旁路画像需要把回音壁基线、照妖镜快照和溯光链路拼成同一张核对映射。",
        "queries": [
            ("旁路画像应该由哪些证据拼起来？", "portal", "forensics"),
            ("怎么区分幽灵读数和真实旁路？", "admin_explore", "night-watch"),
            ("照妖镜与溯光的结果要怎么对齐？", "portal", "quality-audit"),
        ],
    },
)

SEED_DOCUMENT_SPECS = (
    {
        "relative_path": Path("demo-materials/ingest-batch/启明失败回退排演纪要.md"),
        "status": "ready",
    },
    {
        "relative_path": Path("demo-materials/ingest-batch/灰羽名单交接摘录.md"),
        "status": "staged",
    },
    {
        "relative_path": Path("demo-materials/ingest-batch/旁路画像复核纪要.md"),
        "status": "ready",
    },
)

SEED_FEEDBACK_SPEC = {
    "relative_path": Path("demo-materials/text-feedback/图谱体验建议.md"),
    "title": "图谱体验建议",
}


@dataclass(frozen=True, slots=True)
class SeedPaths:
    workspace_root: Path
    kb_path: Path
    state_dir: Path
    db_path: Path
    uploads_dir: Path
    workspaces_dir: Path


def resolve_seed_paths(
    *,
    workspace_root: str | Path | None = None,
    config_path: str | Path | None = None,
) -> SeedPaths:
    if config_path is not None:
        settings = load_settings_for_path(config_path)
        return SeedPaths(
            workspace_root=Path(settings["workspace_root"]).resolve(),
            kb_path=Path(settings["paths"]["knowledge_base"]).resolve(),
            state_dir=Path(settings["paths"]["state_dir"]).resolve(),
            db_path=Path(settings["paths"]["db_path"]).resolve(),
            uploads_dir=Path(settings["paths"]["uploads_dir"]).resolve(),
            workspaces_dir=Path(settings["paths"]["workspaces_dir"]).resolve(),
        )

    workspace = Path(workspace_root or Path(__file__).resolve().parents[1]).expanduser().resolve()
    state_dir = workspace / ".sediment_state"
    return SeedPaths(
        workspace_root=workspace,
        kb_path=workspace / "knowledge-base",
        state_dir=state_dir,
        db_path=state_dir / "platform.db",
        uploads_dir=state_dir / "uploads",
        workspaces_dir=state_dir / "workspaces",
    )


def _seed_feedback_item(store: PlatformStore, *, workspace_root: Path) -> int:
    existing_titles = {
        str(item.get("title") or "")
        for item in store.list_inbox_items(item_type="text_feedback", limit=200)
    }
    title = str(SEED_FEEDBACK_SPEC["title"])
    if title in existing_titles:
        return 0
    content = (workspace_root / SEED_FEEDBACK_SPEC["relative_path"]).read_text(encoding="utf-8")
    submit_feedback_item(
        store=store,
        title=title,
        content=content,
        submitter_name="Sample Contributor",
        submitter_ip="127.0.0.10",
        rate_limit_count=20,
        rate_limit_window_seconds=60,
        dedupe_window_seconds=0,
    )
    return 1


def _seed_document_items(store: PlatformStore, *, workspace_root: Path, uploads_dir: Path) -> int:
    existing_titles = {
        str(item.get("title") or "")
        for item in store.list_inbox_items(item_type="uploaded_document", limit=200)
    }
    created = 0
    for spec in SEED_DOCUMENT_SPECS:
        source_path = workspace_root / spec["relative_path"]
        title = source_path.stem
        if title in existing_titles:
            continue
        filename = source_path.name
        item = submit_uploaded_document_item(
            store=store,
            uploads_dir=uploads_dir,
            filename=filename,
            mime_type=infer_mime_type(filename) or "text/markdown",
            file_bytes=source_path.read_bytes(),
            submitter_name="Sample Contributor",
            submitter_ip="127.0.0.11",
            rate_limit_count=20,
            rate_limit_window_seconds=60,
            dedupe_window_seconds=0,
        )
        target_status = str(spec["status"] or "staged")
        if target_status != "staged":
            store.update_inbox_item(item["id"], status=target_status)
        created += 1
    return created


def _seed_signal_clusters(
    store: PlatformStore,
    *,
    kb_path: Path,
) -> int:
    kb_language = str(inventory(kb_path).get("default_language") or "en")
    proposals_by_id = {str(item["id"]): item for item in list_insight_proposals(kb_path)}
    existing_clusters = {
        str(item.get("cluster_key") or ""): item
        for item in store.list_signal_clusters(limit=500)
    }
    created = 0
    for spec in SEED_CLUSTER_SPECS:
        cluster_key = build_cluster_key(
            language=kb_language,
            intent=str(spec["intent"]),
            normalized_subject=str(spec["normalized_subject"]),
        )
        if cluster_key in existing_clusters:
            cluster = existing_clusters[cluster_key]
            insight_id = str(spec.get("insight_id") or "")
            if insight_id and str(cluster.get("insight_id") or "") != insight_id:
                store.attach_insight_to_cluster(
                    cluster_id=str(cluster["id"]),
                    insight_id=insight_id,
                    status="materialized",
                )
            continue

        for index, (query, entrypoint, actor_name) in enumerate(spec["queries"]):
            query_language = detect_query_language(query, default_language=kb_language)
            normalized_query = normalize_query_for_kb(query, kb_language=kb_language)
            store.record_question_signal(
                raw_query=query,
                normalized_query=normalized_query,
                query_language=query_language,
                kb_language=kb_language,
                response_language=query_language,
                entrypoint=entrypoint,
                strategy="insight-harvest",
                result_mode="synthesized",
                confidence="medium",
                source_entries=list(spec["source_entries"]),
                cluster_key=cluster_key,
                intent=str(spec["intent"]),
                normalized_subject=str(spec["normalized_subject"]),
                actor_fingerprint=fingerprint_actor("examples", str(spec["normalized_subject"]), actor_name, str(index)),
                answer_excerpt=str(spec["answer_excerpt"]),
            )
        cluster = store.get_signal_cluster_by_key(cluster_key)
        if cluster is None:
            raise RuntimeError(f"failed to materialize signal cluster for {cluster_key}")
        insight_id = str(spec.get("insight_id") or "")
        proposal = proposals_by_id.get(insight_id)
        if insight_id:
            cluster = store.attach_insight_to_cluster(
                cluster_id=str(cluster["id"]),
                insight_id=insight_id,
                status="materialized",
            ) or cluster
        emit_explore_graph_events(store=store, cluster=cluster, proposal=proposal)
        created += 1
    return created


def seed_runtime_demo(
    workspace_root: str | Path | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = resolve_seed_paths(workspace_root=workspace_root, config_path=config_path)
    if not paths.kb_path.is_dir():
        raise FileNotFoundError(f"knowledge base not found: {paths.kb_path}")
    ensure_platform_state(
        store=PlatformStore(paths.db_path),
        state_dir=paths.state_dir,
        uploads_dir=paths.uploads_dir,
        workspaces_dir=paths.workspaces_dir,
    )
    store = PlatformStore(paths.db_path)
    feedback_created = _seed_feedback_item(store, workspace_root=paths.workspace_root)
    documents_created = _seed_document_items(
        store,
        workspace_root=paths.workspace_root,
        uploads_dir=paths.uploads_dir,
    )
    clusters_created = _seed_signal_clusters(store, kb_path=paths.kb_path)
    return {
        "workspace_root": str(paths.workspace_root),
        "kb_path": str(paths.kb_path),
        "db_path": str(paths.db_path),
        "seeded_feedback_items": feedback_created,
        "seeded_document_items": documents_created,
        "seeded_clusters": clusters_created,
        "cluster_count": len(store.list_signal_clusters(limit=500)),
        "graph_event_count": len(store.list_graph_events(limit=500)),
        "inbox_count": len(store.list_inbox_items(limit=500)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the official Sediment sample workspace with demo runtime data.",
    )
    parser.add_argument(
        "--workspace",
        default=str(Path(__file__).resolve().parents[1]),
        help="Sample workspace root. Defaults to the checked-in examples directory.",
    )
    parser.add_argument(
        "--config",
        default="",
        help="Optional Sediment config path. If provided, runtime paths are resolved from that config.",
    )
    args = parser.parse_args(argv)
    summary = seed_runtime_demo(
        None if args.config else args.workspace,
        config_path=args.config or None,
    )
    print("Seeded sample runtime state:")
    for key in (
        "workspace_root",
        "db_path",
        "seeded_feedback_items",
        "seeded_document_items",
        "seeded_clusters",
        "cluster_count",
        "graph_event_count",
        "inbox_count",
    ):
        print(f"- {key}: {summary[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

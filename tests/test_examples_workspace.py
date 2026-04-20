from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

from sediment.kb import audit_kb, inventory
from sediment.platform_services import _portal_preview_graph_payload, _universe_graph_payload
from sediment.platform_store import PlatformStore

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_ROOT = REPO_ROOT / "examples"
SAMPLE_KB_ROOT = EXAMPLES_ROOT / "knowledge-base"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_official_sample_workspace_exposes_richer_demo_layers() -> None:
    data = inventory(SAMPLE_KB_ROOT)
    report = audit_kb(SAMPLE_KB_ROOT)

    assert data["default_language"] == "zh"
    assert len(data["entries"]) >= 100
    assert set(data["placeholders"]) == {"静潮窗", "灰羽名单", "旁路画像"}
    assert len(data["insights"]) >= 3
    assert set(data["indexes"]) >= {"index.root", "index.operations", "index.roles", "index.safety"}
    assert report["promotable_placeholder_count"] >= 3
    assert report["canonical_gap_count"] >= 3


def test_official_sample_workspace_home_preview_has_hotspots() -> None:
    payload = _portal_preview_graph_payload(SAMPLE_KB_ROOT)

    assert payload["featured_mode"] == "hotspot"
    assert payload["stats"]["insight_count"] >= 3
    assert payload["focus_seed"].startswith("insight::")
    assert len(payload["hotspots"]) >= 3


def test_example_seed_script_populates_runtime_demo_state(tmp_path: Path) -> None:
    workspace = tmp_path / "sample-workspace"
    shutil.copytree(EXAMPLES_ROOT / "knowledge-base", workspace / "knowledge-base")
    shutil.copytree(EXAMPLES_ROOT / "demo-materials", workspace / "demo-materials")
    script_module = _load_module(
        "seed_runtime_demo",
        EXAMPLES_ROOT / "scripts" / "seed_runtime_demo.py",
    )

    first = script_module.seed_runtime_demo(workspace)
    second = script_module.seed_runtime_demo(workspace)

    db_path = workspace / ".sediment_state" / "platform.db"
    store = PlatformStore(db_path)
    clusters = store.list_signal_clusters(limit=50)
    inbox_items = store.list_inbox_items(limit=50)
    payload = _universe_graph_payload(workspace / "knowledge-base", store=store)

    assert first["cluster_count"] == 3
    assert second["cluster_count"] == 3
    assert len(clusters) == 3
    assert payload["stats"]["query_cluster_count"] == 3
    assert payload["stats"]["event_count"] >= 3
    assert len(payload["hotspots"]) >= 3
    assert any(item["item_type"] == "text_feedback" for item in inbox_items)
    assert any(
        item["item_type"] == "uploaded_document" and item["status"] == "ready"
        for item in inbox_items
    )

from pathlib import Path

from sediment.platform_services import shortest_graph_path
from sediment.platform_store import PlatformStore
from tests.support.platform_harness import build_platform_project


def test_shortest_graph_path_returns_direct_edge(tmp_path: Path) -> None:
    _, kb_path = build_platform_project(tmp_path)
    store = PlatformStore(tmp_path / "platform.db")
    store.init()

    result = shortest_graph_path(
        kb_path,
        source_id="entry::热备份",
        target_id="entry::回音壁",
        store=store,
    )

    assert result["found"] is True
    assert result["node_ids"] == ["entry::热备份", "entry::回音壁"]
    assert [node["id"] for node in result["nodes"]] == ["entry::热备份", "entry::回音壁"]
    assert result["edges"] == [
        {
            "source": "entry::热备份",
            "target": "entry::回音壁",
            "edge_type": "weak_affinity",
        }
    ]


def test_shortest_graph_path_handles_same_and_missing_nodes(tmp_path: Path) -> None:
    _, kb_path = build_platform_project(tmp_path)
    store = PlatformStore(tmp_path / "platform.db")
    store.init()

    same = shortest_graph_path(
        kb_path,
        source_id="entry::热备份",
        target_id="entry::热备份",
        store=store,
    )
    missing = shortest_graph_path(
        kb_path,
        source_id="entry::热备份",
        target_id="entry::不存在",
        store=store,
    )

    assert same["found"] is True
    assert same["node_ids"] == ["entry::热备份"]
    assert [node["id"] for node in same["nodes"]] == ["entry::热备份"]
    assert same["edges"] == []
    assert missing["found"] is False
    assert missing["nodes"] == []

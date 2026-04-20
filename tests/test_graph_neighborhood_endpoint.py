from pathlib import Path

from tests.support.platform_harness import configure_server, build_platform_project


def test_portal_graph_neighborhood_endpoint_returns_focus_slice(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    response = client.get("/api/portal/graph/neighborhood?id=entry::热备份&depth=1")
    assert response.status_code == 200
    payload = response.json()

    assert payload["focus_seed"] == "entry::热备份"
    assert payload["stats"]["depth"] == 1
    assert {node["id"] for node in payload["nodes"]} >= {"entry::热备份", "entry::回音壁"}


def test_portal_graph_neighborhood_endpoint_rejects_bad_requests(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = build_platform_project(tmp_path)
    client, _server_module, _worker_module = configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    missing = client.get("/api/portal/graph/neighborhood")
    bad_depth = client.get("/api/portal/graph/neighborhood?id=entry::热备份&depth=oops")

    assert missing.status_code == 400
    assert bad_depth.status_code == 400

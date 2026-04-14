from __future__ import annotations

from pathlib import Path

from tests.test_platform_workflow import _build_platform_project, _configure_server


def test_web_disorder_admin_actions_require_login(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-1",
    )

    assert client.post("/api/admin/quartz/build", json={}).status_code == 401
    assert client.get("/api/admin/reviews").status_code == 401
    assert client.get("/api/admin/submissions").status_code == 401


def test_web_disorder_invalid_login_then_recover(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-2",
    )

    bad = client.post("/api/admin/session", json={"token": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/admin/session", json={"token": "token-2"})
    assert ok.status_code == 200

    missing = client.post(
        "/api/admin/reviews/review-not-exists/approve",
        json={"reviewer_name": "tester"},
    )
    assert missing.status_code in {400, 404}


def test_web_disorder_logout_then_admin_request_fails(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-3",
    )

    assert client.post("/api/admin/session", json={"token": "token-3"}).status_code == 200
    assert client.delete("/api/admin/session").status_code == 200
    assert client.get("/api/admin/reviews").status_code == 401


def test_web_disorder_out_of_order_entry_update_rejects_missing_entry(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-4",
    )

    assert client.post("/api/admin/session", json={"token": "token-4"}).status_code == 200

    update = client.put(
        "/api/admin/entries/%E4%B8%8D%E5%AD%98%E5%9C%A8%E6%9D%A1%E7%9B%AE",
        json={"content": "# none", "expected_hash": "x", "actor_name": "qa"},
    )
    assert update.status_code == 404


def test_web_disorder_ingest_missing_submission_returns_404(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-5",
    )

    assert client.post("/api/admin/session", json={"token": "token-5"}).status_code == 200
    missing = client.post("/api/admin/submissions/sub-missing/run-ingest")
    assert missing.status_code == 404


def test_web_disorder_double_logout_is_stable(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-6",
    )

    assert client.post("/api/admin/session", json={"token": "token-6"}).status_code == 200
    assert client.delete("/api/admin/session").status_code == 200
    second = client.delete("/api/admin/session")
    assert second.status_code in {200, 401}


def test_web_disorder_admin_job_api_requires_login(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
        admin_token="token-7",
    )

    assert client.get("/api/admin/jobs").status_code == 401
    assert client.get("/api/admin/jobs/job-missing").status_code == 401


def test_web_disorder_portal_submission_invalid_payload_rejected(tmp_path: Path, monkeypatch) -> None:
    project_root, kb_path = _build_platform_project(tmp_path)
    client, _server_module, _worker_module = _configure_server(
        monkeypatch,
        project_root,
        kb_path,
        tmp_path / "state",
    )

    bad = client.post(
        "/api/portal/submissions/text",
        json={
            "title": "",
            "content": "",
            "submitter_name": "tester",
            "submission_type": "concept",
        },
    )
    assert bad.status_code in {400, 422}

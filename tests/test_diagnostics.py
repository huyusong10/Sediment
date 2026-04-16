from __future__ import annotations

from sediment.diagnostics import (
    bind_log_context,
    build_log_record,
    coerce_log_record,
    parse_log_record,
    record_matches_component,
    render_log_record,
    sanitize_log_value,
    serialize_log_record,
)


def test_build_log_record_redacts_secrets_and_trims_large_fields() -> None:
    record = build_log_record(
        component="server",
        event="auth.login",
        message="Admin login attempt.",
        request_id="req-1",
        details={
            "token": "super-secret-token",
            "prompt": "A" * 500,
            "stdout": "B" * 420,
        },
    )

    assert record["component"] == "server"
    assert record["event"] == "auth.login"
    assert record["request_id"] == "req-1"
    assert record["details"]["token"]["redacted"] is True
    assert record["details"]["token"]["fingerprint"]
    assert record["details"]["prompt"]["length"] == 500
    assert record["details"]["stdout"]["length"] == 420


def test_parse_and_render_log_record_round_trip() -> None:
    raw = serialize_log_record(
        build_log_record(
            component="worker",
            event="job.claimed",
            message="Worker claimed a job.",
            job_id="job-123",
            details={"job_type": "tidy"},
        )
    )

    parsed = parse_log_record(raw)

    assert parsed is not None
    assert parsed["component"] == "worker"
    assert record_matches_component(parsed, "worker") is True
    rendered = render_log_record(parsed)
    assert "[worker]" in rendered
    assert "job.claimed" in rendered
    assert "job_id=job-123" in rendered
    assert "job_type=tidy" in rendered


def test_coerce_log_record_keeps_legacy_lines_compatible() -> None:
    legacy = coerce_log_record("[worker] worker boot", default_component="platform")

    assert legacy["component"] == "worker"
    assert legacy["event"] == "legacy.output"
    assert legacy["message"] == "worker boot"
    assert "[worker]" in render_log_record(legacy)


def test_sanitize_log_value_truncates_large_sequences() -> None:
    value = sanitize_log_value(list(range(25)), key="items")

    assert isinstance(value, list)
    assert value[-1]["truncated"] is True


def test_bound_log_context_is_inherited_and_explicit_context_wins() -> None:
    with bind_log_context(request_id="req-ambient", submission_id="sub-ambient"):
        record = build_log_record(
            component="platform_services",
            event="submission.document.created",
            message="Created document submission.",
            submission_id="sub-explicit",
        )

    assert record["request_id"] == "req-ambient"
    assert record["submission_id"] == "sub-explicit"

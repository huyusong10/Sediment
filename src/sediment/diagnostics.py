from __future__ import annotations

import contextvars
import hashlib
import json
import os
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

_LEVELS = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
}
_CORRELATION_KEYS = {
    "request_id",
    "job_id",
    "submission_id",
    "review_id",
    "session_id",
    "user_id",
    "actor_id",
    "workspace_id",
}
_SENSITIVE_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "cookie",
    "authorization",
)
_EXCERPT_KEY_MARKERS = (
    "prompt",
    "content",
    "raw_text",
    "stdin_data",
    "stdout",
    "stderr",
    "output",
    "body",
    "diff",
)
_MAX_EXCERPT_CHARS = 320
_MAX_SEQUENCE_ITEMS = 20
_SINK_LOCK = threading.Lock()
_LOG_CONTEXT: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "sediment_log_context",
    default={},
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_level(level: str) -> str:
    normalized = str(level or "INFO").strip().upper() or "INFO"
    return normalized if normalized in _LEVELS else "INFO"


def _configured_threshold() -> int:
    raw_value = os.environ.get("SEDIMENT_LOG_LEVEL", "INFO")
    return _LEVELS.get(_normalize_level(raw_value), _LEVELS["INFO"])


def _should_emit(level: str) -> bool:
    return _LEVELS[_normalize_level(level)] >= _configured_threshold()


def _fingerprint_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def _trim_text(value: str, *, limit: int = _MAX_EXCERPT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."


def _is_sensitive_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    if normalized.endswith("fingerprint"):
        return False
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _is_excerpt_key(key: str) -> bool:
    normalized = str(key or "").strip().lower()
    return any(marker in normalized for marker in _EXCERPT_KEY_MARKERS)


def _sanitize_scalar(value: Any, *, key: str = "") -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {
            "kind": "bytes",
            "length": len(value),
        }
    if isinstance(value, BaseException):
        return {
            "type": value.__class__.__name__,
            "message": _trim_text(str(value)),
        }

    text = str(value)
    if _is_sensitive_key(key):
        return {
            "redacted": True,
            "length": len(text),
            "fingerprint": _fingerprint_text(text),
        }
    if _is_excerpt_key(key):
        return {
            "excerpt": _trim_text(text),
            "length": len(text),
        }
    if len(text) > _MAX_EXCERPT_CHARS:
        return {
            "excerpt": _trim_text(text),
            "length": len(text),
        }
    return text


def sanitize_log_value(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for item_key, item_value in value.items():
            if item_value is None:
                continue
            sanitized[str(item_key)] = sanitize_log_value(item_value, key=str(item_key))
        return sanitized
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sanitized_items = [
            sanitize_log_value(item, key=key)
            for item in items[:_MAX_SEQUENCE_ITEMS]
        ]
        if len(items) > _MAX_SEQUENCE_ITEMS:
            sanitized_items.append(
                {
                    "truncated": True,
                    "remaining": len(items) - _MAX_SEQUENCE_ITEMS,
                }
            )
        return sanitized_items
    return _sanitize_scalar(value, key=key)


def current_log_context() -> dict[str, Any]:
    return dict(_LOG_CONTEXT.get())


@contextmanager
def bind_log_context(**context: Any):
    updates = {key: value for key, value in context.items() if value is not None}
    merged = current_log_context()
    merged.update(updates)
    token = _LOG_CONTEXT.set(merged)
    try:
        yield
    finally:
        _LOG_CONTEXT.reset(token)


def build_log_record(
    *,
    component: str,
    event: str,
    message: str,
    level: str = "INFO",
    error: BaseException | str | None = None,
    details: dict[str, Any] | None = None,
    **context: Any,
) -> dict[str, Any]:
    ambient_context = current_log_context()
    record: dict[str, Any] = {
        "ts": utc_timestamp(),
        "level": _normalize_level(level),
        "component": str(component or "unknown").strip() or "unknown",
        "event": str(event or "log").strip() or "log",
        "message": str(message or "").strip(),
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
    }
    extra_details = dict(details or {})
    merged_context = dict(ambient_context)
    merged_context.update(context)
    for key, value in merged_context.items():
        if value is None:
            continue
        if key in _CORRELATION_KEYS:
            record[key] = sanitize_log_value(value, key=key)
        else:
            extra_details[key] = value
    if extra_details:
        record["details"] = sanitize_log_value(extra_details, key="details")
    if error is not None:
        if isinstance(error, BaseException):
            record["error"] = {
                "type": error.__class__.__name__,
                "message": _trim_text(str(error)),
            }
        else:
            record["error"] = {"message": _trim_text(str(error))}
    return record


def serialize_log_record(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def write_log_record(sink: TextIO, record: dict[str, Any]) -> None:
    with _SINK_LOCK:
        sink.write(serialize_log_record(record) + "\n")
        sink.flush()


def emit_log(
    sink: TextIO,
    *,
    component: str,
    event: str,
    message: str,
    level: str = "INFO",
    error: BaseException | str | None = None,
    details: dict[str, Any] | None = None,
    **context: Any,
) -> None:
    if not _should_emit(level):
        return
    write_log_record(
        sink,
        build_log_record(
            component=component,
            event=event,
            message=message,
            level=level,
            error=error,
            details=details,
            **context,
        ),
    )


class DiagnosticLogger:
    def __init__(self, component: str, *, sink: TextIO | None = None):
        self.component = str(component or "unknown").strip() or "unknown"
        self.sink = sink

    def _sink(self) -> TextIO:
        import sys

        return self.sink or sys.stdout

    def log(
        self,
        level: str,
        event: str,
        message: str,
        *,
        error: BaseException | str | None = None,
        details: dict[str, Any] | None = None,
        **context: Any,
    ) -> None:
        emit_log(
            self._sink(),
            component=self.component,
            event=event,
            message=message,
            level=level,
            error=error,
            details=details,
            **context,
        )

    def debug(self, event: str, message: str, **context: Any) -> None:
        self.log("DEBUG", event, message, **context)

    def info(self, event: str, message: str, **context: Any) -> None:
        self.log("INFO", event, message, **context)

    def warning(self, event: str, message: str, **context: Any) -> None:
        self.log("WARNING", event, message, **context)

    def error(
        self,
        event: str,
        message: str,
        *,
        error: BaseException | str | None = None,
        **context: Any,
    ) -> None:
        self.log("ERROR", event, message, error=error, **context)

    def exception(self, event: str, message: str, exc: BaseException, **context: Any) -> None:
        self.log(
            "ERROR",
            event,
            message,
            error=exc,
            details={
                "traceback": traceback.format_exception_only(exc.__class__, exc)[-1].strip(),
            },
            **context,
        )


def parse_log_record(line: str) -> dict[str, Any] | None:
    text = str(line or "").strip()
    if not text or not text.startswith("{"):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    required = {"ts", "level", "component", "event", "message"}
    if not required.issubset(payload):
        return None
    return payload


def coerce_log_record(line: str, *, default_component: str = "unknown") -> dict[str, Any]:
    structured = parse_log_record(line)
    if structured is not None:
        return structured

    text = str(line or "").rstrip("\n")
    if not text:
        return build_log_record(
            component=default_component,
            event="legacy.output",
            message="",
        )

    prefix = default_component
    message = text
    if text.startswith("[") and "]" in text:
        prefix = text[1 : text.index("]")] or default_component
        message = text[text.index("]") + 1 :].strip()
    elif " [" in text and "] " in text:
        left, _, rest = text.partition(" [")
        candidate, _, tail = rest.partition("] ")
        if left[:4].isdigit():
            prefix = candidate or default_component
            message = tail.strip()

    return build_log_record(
        component=prefix,
        event="legacy.output",
        message=message,
        details={"raw_line": _trim_text(text)},
    )


def record_matches_component(record: dict[str, Any], component: str) -> bool:
    if component == "all":
        return True
    return str(record.get("component", "")).strip() == component


def render_log_record(record: dict[str, Any]) -> str:
    ts = str(record.get("ts", "")).strip()
    level = str(record.get("level", "INFO")).upper()
    component = str(record.get("component", "unknown")).strip() or "unknown"
    event = str(record.get("event", "log")).strip() or "log"
    message = str(record.get("message", "")).strip()

    correlation_bits = []
    for key in (
        "request_id",
        "job_id",
        "submission_id",
        "review_id",
        "session_id",
        "user_id",
        "actor_id",
        "workspace_id",
    ):
        if record.get(key):
            correlation_bits.append(f"{key}={record[key]}")

    detail_bits = []
    details = record.get("details")
    if isinstance(details, dict):
        for key in sorted(details):
            value = details[key]
            if isinstance(value, (dict, list)):
                detail_bits.append(f"{key}={json.dumps(value, ensure_ascii=False, sort_keys=True)}")
            else:
                detail_bits.append(f"{key}={value}")

    error = record.get("error")
    if isinstance(error, dict):
        error_text = error.get("message") or error.get("type") or ""
        if error_text:
            detail_bits.append(f"error={error_text}")

    parts = [part for part in [ts, level, f"[{component}]", event] if part]
    header = " ".join(parts)
    if correlation_bits:
        header = f"{header} {' '.join(correlation_bits)}"
    if detail_bits:
        return f"{header} | {message} | {'; '.join(detail_bits)}"
    return f"{header} | {message}"

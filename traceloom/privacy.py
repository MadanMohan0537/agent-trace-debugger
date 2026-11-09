"""Deterministic privacy controls applied before trace persistence."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .models import Run, Span


REDACTED_SECRET = "[REDACTED_SECRET]"
REDACTED_EMAIL = "[REDACTED_EMAIL]"

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[^\s,;]+"
)
_SENSITIVE_KEY = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|credential|password|secret)"
)


@dataclass(frozen=True)
class PrivacyPolicy:
    """Top-level structured fields permitted to reach storage."""

    input_allowlist: tuple[str, ...] = (
        "query", "arguments", "side_effect", "idempotent",
        "idempotency_key", "checkpoint",
    )
    output_allowlist: tuple[str, ...] = (
        "recorded", "simulation", "result", "status", "error",
    )


@dataclass(frozen=True)
class PrivacyStats:
    total_fields: int = 0
    retained_fields: int = 0
    dropped_fields: int = 0
    redacted_values: int = 0

    def __add__(self, other: "PrivacyStats") -> "PrivacyStats":
        return PrivacyStats(
            self.total_fields + other.total_fields,
            self.retained_fields + other.retained_fields,
            self.dropped_fields + other.dropped_fields,
            self.redacted_values + other.redacted_values,
        )

    def to_dict(self) -> dict:
        return {
            "total_fields": self.total_fields,
            "retained_fields": self.retained_fields,
            "dropped_fields": self.dropped_fields,
            "redacted_values": self.redacted_values,
            "retained_field_rate": round(
                self.retained_fields / self.total_fields, 6
            ) if self.total_fields else 1.0,
        }


def redact_text(value: str) -> tuple[str, int]:
    """Redact deterministic secret and email patterns from a string."""
    result, email_count = _EMAIL.subn(REDACTED_EMAIL, value)
    result, bearer_count = _BEARER.subn(REDACTED_SECRET, result)
    result, assignment_count = _ASSIGNMENT.subn(REDACTED_SECRET, result)
    return result, email_count + bearer_count + assignment_count


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(item) for item in value.values()) or 1
    if isinstance(value, (list, tuple)):
        return sum(_leaf_count(item) for item in value) or 1
    return 1


def _sanitize_value(value: Any, key: str = "") -> tuple[Any, int]:
    if _SENSITIVE_KEY.search(key):
        return REDACTED_SECRET, _leaf_count(value)
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        clean, redactions = {}, 0
        for child_key, child_value in value.items():
            clean[child_key], count = _sanitize_value(child_value, child_key)
            redactions += count
        return clean, redactions
    if isinstance(value, list):
        clean, redactions = [], 0
        for item in value:
            sanitized, count = _sanitize_value(item)
            clean.append(sanitized)
            redactions += count
        return clean, redactions
    if isinstance(value, tuple):
        clean, redactions = _sanitize_value(list(value), key)
        return clean, redactions
    return value, 0


def sanitize_mapping(payload: dict, allowlist: tuple[str, ...]) -> tuple[dict, PrivacyStats]:
    clean: dict[str, Any] = {}
    total = retained = dropped = redacted = 0
    allowed = set(allowlist)
    for key, value in payload.items():
        leaves = _leaf_count(value)
        total += leaves
        if key not in allowed:
            dropped += leaves
            continue
        clean[key], count = _sanitize_value(value, key)
        retained += leaves
        redacted += count
    return clean, PrivacyStats(total, retained, dropped, redacted)


def sanitize_run(run: Run, policy: PrivacyPolicy = PrivacyPolicy()) -> tuple[Run, PrivacyStats]:
    """Return a sanitized copy and accounting before any database write."""
    task, task_redactions = redact_text(run.task)
    stats = PrivacyStats(redacted_values=task_redactions)
    spans = []
    for span in run.spans:
        clean_input, input_stats = sanitize_mapping(span.input, policy.input_allowlist)
        clean_output, output_stats = sanitize_mapping(span.output, policy.output_allowlist)
        stats = stats + input_stats + output_stats
        spans.append(Span(
            span.run_id, span.span_id, span.sequence, span.kind, span.name,
            span.started_ms, span.duration_ms, span.tokens, span.cost_usd,
            span.status, span.milestone, clean_input, clean_output,
        ))
    return Run(run.run_id, task, run.success, tuple(spans), run.expected_failure), stats

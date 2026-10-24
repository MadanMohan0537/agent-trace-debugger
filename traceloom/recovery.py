"""Safe, deterministic checkpoint-recovery experiments over mocked spans."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .models import Run, Span


@dataclass(frozen=True)
class RecoveryAttempt:
    name: str
    checkpoint_sequence: int
    replay: tuple[Span, ...]
    recovered: bool


def _validate_mock(span: Span, run_id: str) -> None:
    if span.run_id != run_id:
        raise ValueError("replay span belongs to a different run")
    if span.output.get("simulation") is not True:
        raise ValueError("every replay result must be explicitly simulated")
    if span.cost_usd < 0 or not math.isfinite(span.cost_usd):
        raise ValueError("replay costs must be finite and non-negative")


def evaluate_attempt(run: Run, attempt: RecoveryAttempt) -> dict:
    """Evaluate a mocked recovery without executing a recorded tool call."""
    valid_checkpoints = {-1, *(span.sequence for span in run.spans)}
    if attempt.checkpoint_sequence not in valid_checkpoints:
        raise ValueError("checkpoint sequence is not present in the trace")
    if not attempt.replay:
        raise ValueError("recovery attempt requires at least one mocked span")
    for span in attempt.replay:
        _validate_mock(span, run.run_id)

    replayed_original = [
        span for span in run.spans if span.sequence > attempt.checkpoint_sequence
    ]
    repeated_non_idempotent = [
        span.span_id for span in replayed_original
        if span.kind == "tool"
        and span.input.get("side_effect") is True
        and span.input.get("idempotent") is not True
    ]
    cost = round(sum(span.cost_usd for span in attempt.replay), 6)
    return {
        "name": attempt.name,
        "checkpoint_sequence": attempt.checkpoint_sequence,
        "recovered": attempt.recovered,
        "recovery_cost_usd": cost,
        "mocked_spans": len(attempt.replay),
        "repeated_non_idempotent_span_ids": repeated_non_idempotent,
        "safe_for_active_replay": not repeated_non_idempotent,
        "simulation_only": True,
    }


def compare_recovery(
    run: Run, attempts: list[RecoveryAttempt], full_restart_name: str = "full-restart"
) -> dict:
    """Compare successful checkpoints with a required mocked full restart."""
    if run.success:
        raise ValueError("recovery experiments require a failed run")
    names = [attempt.name for attempt in attempts]
    if len(names) != len(set(names)):
        raise ValueError("recovery attempt names must be unique")
    evaluated = [evaluate_attempt(run, attempt) for attempt in attempts]
    full = next((item for item in evaluated if item["name"] == full_restart_name), None)
    if full is None or full["checkpoint_sequence"] != -1:
        raise ValueError("a full restart attempt at checkpoint -1 is required")
    successful = [item for item in evaluated if item["recovered"]]
    safe_successful = [item for item in successful if item["safe_for_active_replay"]]
    recommended = min(safe_successful, key=lambda item: item["recovery_cost_usd"], default=None)
    savings = None
    if recommended and full["recovered"]:
        savings = round(full["recovery_cost_usd"] - recommended["recovery_cost_usd"], 6)
    return {
        "run_id": run.run_id,
        "attempts": evaluated,
        "recommended": recommended["name"] if recommended else None,
        "recovered_attempts": len(successful),
        "safe_recovered_attempts": len(safe_successful),
        "cost_savings_vs_full_restart_usd": savings,
        "decision": "resume" if recommended and recommended["checkpoint_sequence"] >= 0 else "full-restart",
        "simulation_only": True,
    }

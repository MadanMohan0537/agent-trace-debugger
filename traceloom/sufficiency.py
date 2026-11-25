"""Decision-preservation canary for trace privacy policies."""

from __future__ import annotations

from dataclasses import asdict

from .classifier import classify
from .models import Run
from .privacy import PrivacyPolicy, PrivacyStats, sanitize_run
from .recovery import RecoveryAttempt, compare_recovery
from .watchdog import semantic_progress


def _recovery_signature(result: dict) -> dict:
    """Keep every safety fact that can change a restart recommendation."""
    return {
        "recommended": result["recommended"],
        "decision": result["decision"],
        "attempt_safety": {
            item["name"]: item["safe_for_active_replay"]
            for item in result["attempts"]
        },
    }


def diagnostic_sufficiency_canary(
    runs: list[Run],
    recovery_run: Run,
    recovery_attempts: list[RecoveryAttempt],
    policy: PrivacyPolicy = PrivacyPolicy(),
    *,
    max_decision_losses: int = 0,
) -> dict:
    """Compare diagnostic decisions before and after applying ``policy``.

    This is an offline release gate over labeled fixtures. It does not claim
    that the fixtures represent production traffic or that the policy is a
    complete privacy control.
    """
    if isinstance(max_decision_losses, bool) or not isinstance(max_decision_losses, int):
        raise TypeError("max_decision_losses must be an integer")
    if max_decision_losses < 0:
        raise ValueError("max_decision_losses must be non-negative")
    if not runs:
        raise ValueError("at least one diagnostic run is required")

    comparisons: list[dict] = []
    aggregate = PrivacyStats()
    for run in runs:
        sanitized, stats = sanitize_run(run, policy)
        aggregate = aggregate + stats
        before_classification = classify(run)
        after_classification = classify(sanitized)
        before_watchdog = semantic_progress(run.spans)
        after_watchdog = semantic_progress(sanitized.spans)
        comparisons.extend((
            {
                "decision": "failure_classification",
                "run_id": run.run_id,
                "before": before_classification,
                "after": after_classification,
                "preserved": before_classification == after_classification,
            },
            {
                "decision": "semantic_progress_watchdog",
                "run_id": run.run_id,
                "before": asdict(before_watchdog),
                "after": asdict(after_watchdog),
                "preserved": before_watchdog == after_watchdog,
            },
        ))

    clean_recovery, recovery_stats = sanitize_run(recovery_run, policy)
    aggregate = aggregate + recovery_stats
    before_recovery = _recovery_signature(
        compare_recovery(recovery_run, recovery_attempts)
    )
    after_recovery = _recovery_signature(
        compare_recovery(clean_recovery, recovery_attempts)
    )
    comparisons.append({
        "decision": "recovery_safety",
        "run_id": recovery_run.run_id,
        "before": before_recovery,
        "after": after_recovery,
        "preserved": before_recovery == after_recovery,
    })

    losses = [item for item in comparisons if not item["preserved"]]
    return {
        "accepted": len(losses) <= max_decision_losses,
        "max_decision_losses": max_decision_losses,
        "decision_checks": len(comparisons),
        "decision_losses": len(losses),
        "losses": losses,
        "comparisons": comparisons,
        "privacy": aggregate.to_dict(),
        "policy": {
            "input_allowlist": list(policy.input_allowlist),
            "output_allowlist": list(policy.output_allowlist),
        },
        "limitations": [
            "Only the frozen labeled fixtures are covered.",
            "Decision preservation does not prove diagnostic quality or privacy safety.",
            "Payload-dependent diagnostics added later require new canary fixtures.",
        ],
    }

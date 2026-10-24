from .models import Run, Span
from .recovery import RecoveryAttempt


def _span(run,i,kind,name,status="ok",milestone=None,cost=.0002):
    return Span(run,f"{run}-s{i}",i,kind,name,i*100,80,120,cost,status,milestone,{"query":name},{"recorded":True})


def sample_runs() -> list[Run]:
    return [
      Run("run-001","Find and summarize policy",True,(_span("run-001",0,"model","plan",milestone="planned"),_span("run-001",1,"tool","search",milestone="source_found"),_span("run-001",2,"model","answer",milestone="completed"))),
      Run("run-002","Resolve shipment exception",False,(_span("run-002",0,"model","plan",milestone="planned"),_span("run-002",1,"tool","lookup"),_span("run-002",2,"tool","reroute"),_span("run-002",3,"tool","notify"),_span("run-002",4,"model","replan")),"infinite_loop"),
      Run("run-003","Fetch weather",False,(_span("run-003",0,"model","plan",milestone="planned"),_span("run-003",1,"tool","weather",status="timeout")),"timeout"),
      Run("run-004","Book restricted item",False,(_span("run-004",0,"model","plan",milestone="planned"),_span("run-004",1,"model","answer",status="refused")),"refusal"),
      Run("run-005","Research options",True,(_span("run-005",0,"model","plan",milestone="planned"),_span("run-005",1,"tool","search"),_span("run-005",2,"tool","search"),_span("run-005",3,"tool","search",milestone="source_found"),_span("run-005",4,"model","answer",milestone="completed"))),
    ]


def recovery_fixture() -> tuple[Run, list[RecoveryAttempt]]:
    """Frozen failure with one safe checkpoint and one unsafe earlier resume."""
    run_id = "recovery-001"
    failed = Run(
        run_id,
        "Confirm shipment and notify customer",
        False,
        (
            Span(run_id, "plan", 0, "model", "plan", 0, 50, cost_usd=.001,
                 milestone="planned"),
            Span(run_id, "lookup", 1, "tool", "lookup", 50, 80, cost_usd=.002,
                 milestone="shipment_found",
                 input={"side_effect": False, "idempotent": True}),
            Span(run_id, "reserve", 2, "tool", "reserve_slot", 130, 90,
                 cost_usd=.004, milestone="slot_reserved",
                 input={"side_effect": True, "idempotent": False}),
            Span(run_id, "notify", 3, "tool", "notify", 220, 100,
                 cost_usd=.003, status="timeout",
                 input={"side_effect": True, "idempotent": True,
                        "idempotency_key": "notify-recovery-001"}),
        ),
        "timeout",
    )

    def mock(span_id: str, sequence: int, name: str, cost: float) -> Span:
        return Span(
            run_id, span_id, sequence, "tool", name, sequence * 100, 50,
            cost_usd=cost, output={"simulation": True, "result": "ok"},
        )

    attempts = [
        RecoveryAttempt(
            "full-restart", -1,
            (
                mock("full-plan", 10, "plan", .001),
                mock("full-lookup", 11, "lookup", .002),
                mock("full-reserve", 12, "reserve_slot", .004),
                mock("full-notify", 13, "notify", .003),
            ),
            True,
        ),
        RecoveryAttempt(
            "after-lookup", 1,
            (mock("retry-reserve", 20, "reserve_slot", .004),
             mock("retry-notify", 21, "notify", .003)),
            True,
        ),
        RecoveryAttempt(
            "after-reservation", 2,
            (mock("retry-notify-only", 30, "notify", .003),),
            True,
        ),
    ]
    return failed, attempts



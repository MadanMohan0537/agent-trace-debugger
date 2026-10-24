# Architecture and data boundaries

## Span contract

A span has a run ID, stable span ID, monotonic sequence, kind, name, start time, duration, tokens, cost, status, optional milestone, and structured input/output. TraceLoom validates sequence uniqueness, persists JSON with stable key ordering, and replays spans by sequence.

## Decisions

| Decision | Rationale | Tradeoff |
|---|---|---|
| Local SQLite store | Zero-service reproducible MVP | Not a distributed telemetry backend |
| OpenTelemetry-shaped concepts | Easier future adapter path | Not wire-compatible OTLP yet |
| Store raw recorded tool results | Deterministic replay and diagnosis | Raises privacy and retention risk |
| Explicit success label | Needed for cost per success and silent errors | Labels can be delayed or subjective |
| Six-class taxonomy | Actionable without excessive fragmentation | `unknown` remains necessary |
| Explicit milestones | Detects progress across different actions | Requires task-aware instrumentation |
| Static HTML console | Portable and credential-free | No interactive filtering or auth |
| Mocked recovery only | Measures restart decisions without executing side effects | Mock outcomes may not transfer to live tools |
| Exclude non-idempotent repeats | Avoids recommending obviously unsafe resume points | Depends on complete tool metadata |

## Safe replay boundary

This MVP never re-executes tool calls. It shows stored input and output records. Any future active replay must classify tool idempotency, simulate writes by default, prevent duplicated side effects, and maintain an approval/audit path.

## Recovery experiment boundary

A recovery attempt names an existing checkpoint and supplies one or more
explicitly simulated replay spans. An attempt without output.simulation=true
is rejected. Checkpoint -1 is the mandatory full restart comparator. The
evaluator lists every original non-idempotent tool that would be repeated and
recommends only the cheapest successful candidate with none.

This is a decision experiment, not an executor. It neither invokes tools nor
asserts that a mocked success reproduces production state. Active recovery
requires postcondition checks, idempotency enforcement, approvals for writes,
and an append-only provenance record.

## Production hardening

Add OTLP ingestion, tenant isolation, field allowlists and redaction before persistence, encryption, retention enforcement, authenticated query access, clock-skew handling, sampling, backpressure, versioned classifiers, and a label-feedback loop. Benchmark taxonomy precision and watchdog thresholds on representative reviewed traces before paging operators.



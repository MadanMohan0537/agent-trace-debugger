# Architecture and data boundaries

## Span contract

A span has a run ID, stable span ID, monotonic sequence, kind, name, start time, duration, tokens, cost, status, optional milestone, and structured input/output. TraceLoom validates sequence uniqueness, persists JSON with stable key ordering, and replays spans by sequence.

## Decisions

| Decision | Rationale | Tradeoff |
|---|---|---|
| Local SQLite store | Zero-service reproducible MVP | Not a distributed telemetry backend |
| OpenTelemetry-shaped concepts | Easier future adapter path | Not wire-compatible OTLP yet |
| Sanitize before opening the write transaction | Prevent known secret patterns and unapproved fields from reaching SQLite | Pattern matching is incomplete and allowlists reduce evidence |
| Explicit success label | Needed for cost per success and silent errors | Labels can be delayed or subjective |
| Six-class taxonomy | Actionable without excessive fragmentation | `unknown` remains necessary |
| Explicit milestones | Detects progress across different actions | Requires task-aware instrumentation |
| Static HTML console | Portable and credential-free | No interactive filtering or auth |
| Mocked recovery only | Measures restart decisions without executing side effects | Mock outcomes may not transfer to live tools |
| Exclude non-idempotent repeats | Avoids recommending obviously unsafe resume points | Depends on complete tool metadata |
| Inject retention time | Makes TTL behavior reproducible and testable | Production callers must provide a trusted clock |

## Privacy firewall boundary

The persistence path is `Run -> sanitize_run -> SQLite transaction`. Input and output payloads have separate top-level allowlists. Permitted nested structures keep diagnostic shape, but sensitive key names are replaced and string values are scanned for email addresses, bearer tokens, and common secret assignments. The task string is scanned too. Unknown top-level payload fields are dropped.

The firewall emits per-run field counts. “Retained” includes values that were retained in redacted form, so the retention rate is an evidence-volume indicator—not a privacy guarantee or a measure of diagnostic sufficiency. The policy is code-defined and deterministic in this increment.

TTL cleanup is an explicit, injected-clock operation. It removes runs, spans, and privacy accounting together. This MVP does not schedule cleanup, sanitize pre-existing rows retroactively, inspect binary payloads, or detect obfuscated secrets.

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

Add OTLP ingestion, tenant isolation, encryption, scheduled retention enforcement, authenticated query access, clock-skew handling, sampling, backpressure, versioned classifiers, and a label-feedback loop. Add policy provenance and measure classifier/watchdog decision loss after sanitization. Benchmark taxonomy precision and watchdog thresholds on representative reviewed traces before paging operators.



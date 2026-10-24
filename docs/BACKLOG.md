# Rigorous feature backlog

P1 semantic progress monitoring and the P2 simulated recovery experiment are implemented. The remaining items are proposals, not completed functionality.

| Priority | Feature | Concrete user problem | Intended behavior | Dependencies | Success test | Risks and tradeoffs |
|---|---|---|---|---|---|---|
| P1 shipped | Semantic progress watchdog | Changing actions can loop without triggering repeated-tool rules | Track task milestones and flag bounded action windows with no change | Milestone contract, labeled scripted traces | Higher loop recall than repeated-tool detection without higher false alerts on frozen fixtures | Useful exploration may look stagnant; support task grace periods |
| P2 shipped | Recovery checkpoint experiment | Debuggers cannot tell which restart point is worth trying | Compare explicitly mocked checkpoint resumes with a full restart; report cost and repeated non-idempotent spans | Recorded trace, simulation marker, idempotency metadata, cost model | Frozen task recovers from the safe checkpoint for $0.007 less than restart and rejects two unsafe candidates | Mock success may not transfer; metadata can be wrong; no live execution |
| P2 | Trace privacy firewall | Raw prompts and tool results may expose secrets | Apply allowlists, structured redaction, TTLs, and retained-field accounting before storage | Data classification policy, deletion job | Seeded secrets never reach SQLite and expired traces disappear | Over-redaction can destroy diagnostic value |
| P2 | Taxonomy calibration queue | Rules silently misclassify failures | Sample runs by uncertainty and impact for blinded reviewer labels | Reviewer workflow, versioned classifier | Improve macro precision on a held-out labeled trace set | Reviewer disagreement may make labels unstable |
| P3 | Critical-path attribution | Total latency does not reveal which parallel branch delayed completion | Reconstruct dependency graph and identify critical-path spans | Parent/link span IDs, clock normalization | Identify the seeded blocking branch in parallel fixtures | Bad clocks and missing links distort attribution |
| P3 | Spend-blast-radius alert | A failing agent can burn budget before success rate moves | Forecast remaining run cost and stop within a task-level budget policy | Streaming spans, policy engine | Halt seeded runaway traces before the declared cap with measured false stops | Early stopping may abort recoverable runs |
| P3 | Counterfactual fix recommender | Operators know the failure class but not the cheapest fix | Replay prompt, schema, or model configuration changes against frozen traces | Versioned configurations, recovery harness | Recommended fix wins on recovery cost in held-out scripted incidents | Offline replay may not transfer to live tools |
| P3 | Recovery state-equivalence check | A resumed task may report success with different downstream state | Compare declared postconditions and state snapshots across restart and resume | Domain invariants, normalized snapshots | Seeded partial-recovery fixture is rejected despite a successful final response | Snapshot scope may miss hidden state |
| P3 | Checkpoint provenance seal | Operators cannot prove which trace and mock set produced a recommendation | Hash the source trace, checkpoint policy, mocks, and cost model into the report | Canonical serialization, version registry | Any changed input invalidates the prior recommendation digest | Hashes prove identity, not correctness |
| P3 | Novel failure clustering | The fixed taxonomy hides emerging modes inside `unknown` | Cluster redacted unknown traces and require reviewer naming before taxonomy changes | Embeddings or feature vectors, privacy firewall | Seeded novel family forms a stable cluster without splitting known classes | Clusters may reflect wording rather than cause |
| P4 | SLO budget by task class | One global threshold penalizes complex tasks | Configure success, latency, and cost budgets by versioned task class | Task classifier, policy registry | Frozen tasks are judged only against their declared class | Misclassification can hide regressions |

## Next slice

Build the trace privacy firewall next. Apply allowlisted field retention,
structured secret redaction, and deterministic TTL deletion before raw prompts
or tool results reach SQLite. Verify against seeded secrets while measuring how
much diagnostic context is removed.



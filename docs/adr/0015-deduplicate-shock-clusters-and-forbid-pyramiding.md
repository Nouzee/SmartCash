# Deduplicate shock clusters and forbid pyramiding

SmartCash permits at most one active Candidate Shock and one open Trade Episode per symbol. Same-direction anomalies observed before re-arming update the existing cluster's diagnostics but do not create new signal IDs, orders, or position increments. After expiry or exit, the trigger state must return to the non-anomalous region for two consecutive checkpoints containing fresh market events before the symbol becomes re-armed.

## Consequences

- SmartCash does not pyramid either deployable long positions or experimental short positions.
- An opposite confirmation may close an episode but cannot reverse the position in the same step.
- Every shock cluster, candidate, intent, order, fill, and episode retains linked unique IDs in the ledger.
- This is a SmartCash high-frequency rule, not a Hitchhike behavior; Hitchhike contributes only the useful precedent of unique signal IDs and event-level ledger rows.

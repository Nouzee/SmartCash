# Phase 1 — Beast Vault transform handoff

Date: 2026-07-13 (Asia/Shanghai)

## Status

Vault does contain persisted `hktransaction + l2thousand` source data. Real-data quality reports can now run, while factor estimation and performance backtests remain `BLOCKED_FOR_EMPIRICAL_CLAIMS` because the archived files do not prove a complete live capture or the trade-direction convention.

Engineering is not blocked. A Beast-owned transform entry point now exists under `/home/zrliu/thousand/backend/beast_tools/smartcash/`. It accepts a pinned Vault JSONL export plus independent capture evidence and emits:

- canonical arrival-ordered `events.jsonl`;
- a Vault dataset / Beast full-commit / config / artifact hash lineage manifest;
- capture evidence preserving the input-export hash and bound to the emitted event hash;
- a transform summary that explicitly disables empirical claims.

The public transform CLI seam is covered by fixture tests plus parameterized
source-rejection cases. They prove deterministic hash-bound output, input-order
preservation, explicit direction provenance, exact expected-universe capture
evidence and rejection of broker queue aliases, incomplete source pairs and
non-Hong-Kong arrival timestamps. The fixtures are synthetic contract evidence
only; they are not market evidence.

A second Beast entry point, `python -m beast_tools.smartcash.octopus_live`, now
reads `/vault/core/data/Octopus-Live/PROD/<date>/realtime` directly. It selects
only `tick_archiver` and `l2thousand_enhancer`, preserves raw payloads, sorts by
filesystem `mtime_ns`, hashes the selected source snapshot, and reports broker
queue files as ignored. Since `mtime_ns` is only a persisted save-time proxy,
its summary always records `capture_evidence_available=false` and
`empirical_claims_allowed=false`.

The first actual export and SmartCash quality-only run covered 2026-01-08
`00700.HK`. Exact findings are in
[the Vault quality report](phase-02-vault-quality-2026-01-08-00700.md). This
engineering completion changes “data unavailable” to “data found but not yet
empirically admissible.”

## Resume point

1. Find or collect independent capture ACK/heartbeat/drop-counter evidence for a complete session.
2. Verify the direction convention independently and add an as-of identity map.
3. Bind an admissible export through `python -m beast_tools.smartcash` with the Vault dataset ID/version/content hash and the full Beast commit.
4. Run SmartCash `--quality-only`; only after lineage, capture envelope, side verification and coverage all pass may replay generate features and labels.

No market-making code, production webpage, CCASS holdings semantics, or broker-queue-as-trade behavior was added.

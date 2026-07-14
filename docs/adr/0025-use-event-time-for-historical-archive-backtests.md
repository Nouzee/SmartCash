# Use event time for historical archive backtests

SmartCash supports a distinct historical-archive backtest mode for frozen
Vault Octopus-Live exports.  It is for offline research, not a claim about
live ingestion latency, live completeness, or executable fills.

## Decision

`historical_archive_backtest` requires a hash-bound
`octopus-export-summary.json`, a hash-bound Vault/Beast lineage manifest,
matching `hktransaction` and `l2thousand` events for every requested symbol,
and an explicit verified direction convention.  The exporter summary and the
lineage manifest must agree on both the source-snapshot hash and export hash.
It replays events on the exchange `event_ts` clock, with a fixed book-first
tie-break for equal timestamps.  Persisted file mtime remains recorded as
provenance but cannot define what was known in real time.

The mode does not require a subscription acknowledgement, heartbeat ledger, or
dropped-callback counter.  Those are live-capture controls and remain required
for `historical_replay` and `live_session_capture` claims that depend on
arrival-time causality.

## Consequences

- The resulting manifest declares `replay_clock=event_time_assumed`,
  `historical_backtest_allowed=true`, and
  `realtime_capture_evidence_required=false`, as well as
  `live_claims_allowed=false` and `executable_claims_allowed=false`.
- It preserves and publishes tape, L2-gap, stale-arrival, and input-quality
  diagnostics; archive gaps are not silently treated as complete coverage.
- Archive results may support exploratory historical factor and markout
  research.  They do not validate latency-sensitive signals, real-time
  availability, Protected IOC fills, or deployment promotion.
- The full source snapshot and export hashes bind every run to immutable input
  material.  Broker queue remains inadmissible as either trade or L2 input.

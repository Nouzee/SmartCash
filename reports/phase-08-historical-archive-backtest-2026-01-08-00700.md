# Phase 8 — historical archive backtest

Run date: 2026-07-14 (Asia/Shanghai)

## Decision

The 2026-01-08 `00700.HK` Vault archive is usable for an **exploratory
event-time historical backtest**.  It is not evidence about real-time
availability, latency, complete tape capture, executable fills, or deployment
performance.

This run supersedes the earlier decision only for the newly defined
`historical_archive_backtest` mode.  It does not alter the factual capture
findings in Phases 2–7 or make the archive eligible for a live-causality claim.

## Immutable input

- Vault source: `/vault/core/data/Octopus-Live/PROD/20260108/realtime`
- Export: `/tmp/smartcash-historical-20260108-00700/export/vault-export.jsonl`
- Export summary: `/tmp/smartcash-historical-20260108-00700/export/octopus-export-summary.json`
- Vault/Beast lineage: `/tmp/smartcash-historical-20260108-00700/vault-beast-manifest.json`
- Source snapshot SHA-256:
  `afe1632e9b569ae5161708fb8ee63eb940506256ee33d0a8ca4c43b242e2e07b`
- Export SHA-256:
  `ddba4b5dea996f08bdef9db53e94b9b43a94392ea796d882952c91e53c88e84b`
- Requested symbol: `00700.HK`
- Selected source rows: 10,717 `hktransaction` and 12,275 `l2thousand`
  snapshots. Four crossed/locked books were rejected during normalization.

The run uses the documented XTQuant convention `Dir=1 → sell`, `Dir=2 → buy`.
Its side-verification artifact points to the vendor L2 specification recorded
in Phase 3.

## Backtest contract

The historical source summary and Vault/Beast lineage manifest jointly
hash-bind the selected source snapshot and export.  The manifest records the
Beast exporter (`beast_tools.smartcash.octopus_live`), its immutable commit,
and its configuration hash.  The replay intentionally replaces persisted
file-mtime arrival proxies with each event's exchange `event_ts`, uses a
documented deterministic tie-break for equal timestamps, and declares
`replay_clock=event_time_assumed`.  It explicitly sets
`live_claims_allowed=false` and `executable_claims_allowed=false`; it does not
claim those events were available at those times in a live process.

The complete output is in
`/tmp/smartcash-historical-20260108-00700/backtest-hardened-10s/` and includes
`feature_snapshots.csv`, `markout_labels.csv`, `backtest_summary.csv`, shock
outputs, `data_quality_report.csv`, and `manifest.json`.

## Result inventory

| Field | Value |
| --- | ---: |
| Accepted normalized events | 22,988 |
| Feature snapshots (10-second checkpoints) | 2,053 |
| Future markout labels | 6,148 |
| Shock events / outcomes | 115 / 90 |
| Largest active-session L2 gap | 593.451 seconds |
| Trade sequence gaps | 10,715 |
| Complete live capture window | false |
| Historical backtest allowed | true |

The summary tables are descriptive outputs from one symbol-day.  They are not
an alpha estimate: the source has material L2 gaps and tape discontinuities,
the cadence is 10 seconds rather than the default one second, no point-in-time
identity map was supplied, and no fees, impact stress, or real fills are
included.

## Next action

Run the same hash-bound event-time mode across the 2026-01-06 through
2026-01-09 archive days and report results by day before any threshold choice
or walk-forward evaluation.  The default one-second replay needs a performance
pass before it is used for the full archive set.

# Phase 6 — server capture-evidence search

Run date: 2026-07-14 (Asia/Shanghai)

## Decision

**Required SmartCash capture evidence is unavailable.  Skip these server
archives for empirical/alpha work.**

The search found genuine, durable `hktransaction` event streams and separate
`l2thousand` snapshot material, but no archive contains the required paired
native streams plus a provider-issued, per-`symbol × period` subscription
receipt, a durable stream heartbeat ledger, and stream-level dropped-callback
accounting.  This is a data-lineage decision, not a claim that the existing
data are false or useless for operational diagnosis.

Consequently the current SmartCash state remains
`BLOCKED_FOR_EMPIRICAL_CLAIMS`.  These artifacts may be inspected for
engineering/debugging, but must not be converted into a quality-passing
dataset, backtest result, or alpha conclusion.

## Acceptance rule used

For every expected `symbol × {hktransaction, l2thousand}` stream, accept only
an archive with all of the following:

1. raw paired native events;
2. a provider-controlled acknowledgement containing stream identity, outcome,
   provider time, and a stable receipt/event ID;
3. durable capture-time heartbeats spanning the session; and
4. durable received/enqueued/rejected/dropped counters for that stream, with
   the quality gate's drop condition satisfied.

A local SDK handle, global quote-server connection state, first callback, or a
frontend/gateway `subscribe_ack` is explicitly not a provider acknowledgement.
This is the same contract recorded in Phase 4 and Phase 5.

## Search scope and method

Read-only filename and content searches covered:

| Root | Filename search | Content search |
| --- | --- | --- |
| `/vault/core/data` | data units, `l2thousand`, manifests, heartbeats | `provider ack`, subscription acknowledgement/receipt, paired stream names |
| `/vault/core/storage` | recordings, event/heartbeat files, manifests | same acknowledgement and stream terms |
| `/home/hliu` (bounded) | `thousand`, `thousand-broker-queue-price-levels`, `beast`, `xtbackend`, `__runtime__/xtquant`, and PM2 logs; excluded source-control, package caches, virtual environments, and opaque database binaries | provider-ACK/receipt variants, `subscription_ack`, `hktransaction`, `l2thousand`, heartbeat, and dropped/rejected-counter variants |
| `/home/zrliu/thousand` | runtime artifacts, tools, configuration, docs, and existing capture code | the same patterns, with local code used only to interpret artifact semantics |

The raw-spool search examined every
`*/spool/raw_market_events.jsonl` below both Thousand artifact roots, counting
the exact serialized periods `"hktransaction"` and `"l2thousand"`.  The
provider-ack search used case-insensitive forms of `provider.*ack|receipt|acknowledg`,
`subscription.*provider|receipt|acknowledg`, and an acknowledged stream form.
It returned no provider-ack artifact in the searched server-data roots.

## Positive candidates, and disposition

| Candidate | What is present | Why it is rejected for SmartCash |
| --- | --- | --- |
| `/home/hliu/thousand-broker-queue-price-levels/artifacts/runtime-state-v3*/YYYYMMDD/spool/raw_market_events.jsonl` | Large real-looking, hash-bearing raw event journals.  For example, 2026-07-13 includes `00700.HK` and `00939.HK` `hktransaction` records with receive/source timestamps, payload hashes, price, volume, turnover and side.  Many historical dates contain tens of thousands of exact `hktransaction` rows. | Exact scan found **zero `l2thousand` rows in every raw spool**.  The other high-volume stream is `hkbrokerqueueex`/broker queue, which is not a substitute.  No per-stream provider receipt or capture envelope is present. |
| `/home/hliu/thousand/artifacts/market-terminal-v3-local/20260609-real*-collector-silver608-9020/` | Real-run raw spools contain `hktransaction` (e.g. 99,146 rows in the `real11-02723` spool) and runtime-health files. | No `l2thousand` row was found.  Health is an operational aggregate and cannot provide the missing receipt/stream coverage.  Moreover the `real11` health records aggregate dropped counts including 74 (final file: 8), so it cannot establish the zero-drop requirement anyway. |
| `/vault/core/storage/lynx-market-data/recordings/dark-market-wide/20260625/` | Per-symbol `hktransaction-*.ndjson`, local `event:"subscribed"` entries, per-file heartbeat/count material. | The paired file type is `l2quote`, not native `l2thousand`; all 535 rows per stream have empty `raw:[]`; coverage is only about 10 minutes.  Local subscription IDs/counts lack provider ACK/receipt fields and stream drop accounting. |
| `/vault/core/data/Octopus-Live/PROD/20260106..20260109/realtime/l2thousand_enhancer_*.json` | 59,565 `l2thousand` snapshots over the four dates (9,521 / 15,766 / 17,995 / 16,283). | There is no same-session `hktransaction` companion, provider receipt, capture heartbeat ledger, or dropped-callback accounting.  A snapshot is not a capture-evidence chain. |
| Thousand runtime-health, callback-rejection, cloud relay, and full-chain-debug artifacts | Diagnostics include aggregate callback counts, local health heartbeats, and `subscribe_ack` protocol frames. | These signals describe local runtime/gateway state.  They do not bind a provider acknowledgement to symbol and period.  Existing Phase 4/5 source audit shows the upstream SDK only exposes a local integer handle and global connection watch. |

## Supporting primary-source interpretation

The server findings agree with the local first-party implementation audit:

- [`smartcash_live_capture.py`](/home/zrliu/thousand/backend/tools/smartcash_live_capture.py:128)
  deliberately declares `provider_acknowledgement_recorded: false`.
- [`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:91)
  refuses a provider-ack claim without a real adapter.
- [`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:375)
  retains subscription handles locally; this is not durable provider evidence.
- [`data_quality.py`](/home/zrliu/smartcash/src/smartcash/data_quality.py:80)
  requires acknowledgement, heartbeat coverage, and no dropped callbacks.

## Next action

Leave this data component empty and proceed with work that does not assert
empirical performance.  When a future full-day capture provides the four
acceptance-rule components above, run the Vault/Beast transform followed by
SmartCash `--quality-only`; only a passing result may unblock empirical work.

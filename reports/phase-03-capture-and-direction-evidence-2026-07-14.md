# Phase 3 — Capture and direction evidence audit

Run date: 2026-07-14 (Asia/Shanghai)

Market session: 2026-01-08

Symbol: `00700.HK`

## Decision

The frozen 2026-01-08 `00700.HK` session **cannot pass either current gate**:

| Gate | Current result | Why |
| --- | --- | --- |
| Independent full-session capture | **FAIL** | The Vault archive has only a filesystem-mtime arrival proxy; it has no hash-bound capture envelope with a durable subscription acknowledgement, full-session heartbeat series, or dropped-callback count. This cannot be recreated truthfully after the fact. |
| Direction verification | **FAIL (current replay)** | The replay manifest records `side_verified: false`; no reviewed side-verification artifact was supplied. The underlying `Dir` mapping is now documented authoritatively, so this gate is remediable by an artifact that meets SmartCash's side-verification contract—not by guessing or by using the legacy inverse mapping. |

The direction mapping to use is `xtquant_vendor_doc_dir_1_sell_2_buy`:

- `Dir=0`: other / neutral;
- `Dir=1`: seller aggresses an existing bid, therefore **SELL** aggressor;
- `Dir=2`: buyer aggresses an existing ask, therefore **BUY** aggressor.

The mapping does not repair the capture failure, tape discontinuities, stale rows, or L2 gaps already recorded for this session. It only resolves the vendor-direction ambiguity.

## Audit provenance and limitations

This audit pins the persisted source snapshot SHA-256
`afe1632e9b569ae5161708fb8ee63eb940506256ee33d0a8ca4c43b242e2e07b`
and its Vault export SHA-256
`ddba4b5dea996f08bdef9db53e94b9b43a94392ea796d882952c91e53c88e84b`,
as recorded by the export summary below. The reviewed Beast transform revision
is `0a9eab63b93e4159cbca8a269ebacc9c0fe8a13b`; the SmartCash contract revision
is `249124bd43899921e68b9059dcd868a3dc4ff231`.

No Vault dataset ID/version/content hash or Beast transform-config hash was
available for this archived run. These omissions are part of why it is an audit
subject rather than an admissible Vault/Beast artifact; this report does not
claim to supply the missing lineage manifest.

## Primary-source findings

### The 2026-01-08 Vault files are not independent capture evidence

The Vault source row is a `tick_archiver` `tick_raw` result containing `Time`,
`Seq`, `Dir`, and the raw trade fields, but no subscription or monitor envelope:
[`tick_archiver_20260108_093000.json`](/vault/core/data/Octopus-Live/PROD/20260108/realtime/tick_archiver_20260108_093000.json:2).

The Beast-owned exporter explicitly identifies filesystem `mtime_ns` as its
only persisted arrival-time proxy and says the output remains quality-only
until an independent callback-capture envelope is supplied:
[`octopus_live.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/octopus_live.py:1).
It derives `captured_at` from file mtime, labels it `vault_file_mtime_ns`, and
does not read an ACK, heartbeat, or dropped-callback record:
[`octopus_live.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/octopus_live.py:49).

The pinned export summary confirms that exact condition for this session:
`capture_evidence_available=false`, `captured_at_source=vault_file_mtime_ns`,
and 22,992 selected source files (10,717 trades and 12,275 books):
[`octopus-export-summary.json`](/home/zrliu/smartcash/artifacts/vault-quality-20260108-00700-export-v2/octopus-export-summary.json:2).

SmartCash's capture contract requires source `xtquant.hktransaction`, a
subscription acknowledgement before the expected open, ordered heartbeats from
open through expected end with gaps no greater than 60 seconds, and zero
dropped callbacks:
[`data_quality.py`](/home/zrliu/smartcash/src/smartcash/data_quality.py:81).
The frozen quality replay supplies no capture-evidence file and reports
`trade_capture_complete=false`:
[`manifest.json`](/home/zrliu/smartcash/artifacts/vault-quality-20260108-00700-final/manifest.json:7).

### Current capture code has useful partial mechanics, but not the required durable envelope

The active Beast/Thousand XTQuant client records received, enqueued, and
rejected callbacks in an in-memory stats object:
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:30).
Its callback increments those counters, including `callback_rejections`:
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:390).
Subscriptions store each returned handle and count calls, but do not record a
provider-side ACK as a durable capture artifact:
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:145).

The separate Vault recorder does persist a `subscribed` event after
`subscribe_quote` returns and persists raw callback payloads:
[`auction_recorder.py`](/home/hliu/lynx-dev/services/market-data/src/market_data/realtime/auction_recorder.py:214),
[`auction_recorder.py`](/home/hliu/lynx-dev/services/market-data/src/market_data/realtime/auction_recorder.py:236).
Its heartbeat contains only status, update time, and writer counts—not
callback received/dropped counters:
[`auction_recorder.py`](/home/hliu/lynx-dev/services/market-data/src/market_data/realtime/auction_recorder.py:315).

One later recorder run demonstrates the partial evidence: it records
`hktransaction` subscription-return IDs:
[`events.ndjson`](/vault/core/storage/lynx-market-data/recordings/dark-market-wide/20260625/events.ndjson:4).
But its configuration uses `l2quote`, not `l2thousand`:
[`metadata.json`](/vault/core/storage/lynx-market-data/recordings/dark-market-wide/20260625/metadata.json:10),
and its last heartbeat is at 16:26 despite a 19:00 scheduled end:
[`heartbeat.json`](/vault/core/storage/lynx-market-data/recordings/dark-market-wide/20260625/heartbeat.json:2),
[`metadata.json`](/vault/core/storage/lynx-market-data/recordings/dark-market-wide/20260625/metadata.json:22).
It is therefore not a substitute for the 2026-01-08 session or a qualifying
SmartCash dataset.

### XTQuant direction semantics are authoritative and match SmartCash's vendor convention

The local XTQuant/Beast vendor document defines `hktransaction.dir` and
explicitly states `0=other`, `1=seller aggresses an existing buy order`, and
`2=buyer aggresses an existing sell order`; it also identifies `brokerNo` as
passive and `activeBrokerNo` as active:
[`港股L2数据原生_v3.9.md`](/home/hliu/beast/港股L2数据原生_v3.9.md:378).

SmartCash projects that contract as `Dir=1 -> SELL`, `Dir=2 -> BUY`, and keeps
all other values neutral:
[`xtquant.py`](/home/zrliu/smartcash/src/smartcash/xtquant.py:44).
The Beast transform defaults to precisely this convention:
[`__init__.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/__init__.py:120).
The 2026-01-08 raw source does carry the native `Dir` field (for example,
`Dir=2`):
[`tick_archiver_20260108_093000.json`](/vault/core/data/Octopus-Live/PROD/20260108/realtime/tick_archiver_20260108_093000.json:5).

However, the existing quality replay did not include SmartCash's required
side-verification artifact and consequently records `side_verified=false`:
[`manifest.json`](/home/zrliu/smartcash/artifacts/vault-quality-20260108-00700-final/manifest.json:7).
SmartCash rejects a side-verification artifact unless it is explicitly
approved, time-stamped, contains evidence, and matches the selected convention:
[`cli.py`](/home/zrliu/smartcash/src/smartcash/cli.py:136).

## Required next tracer

Capture a new complete session prospectively for every target symbol with both
`hktransaction` and `l2thousand`. Persist the following independent capture
envelope and lineage artifacts:

1. a per-symbol durable subscription acknowledgement before the expected open.
   A client-side subscription return or handle may be recorded for diagnosis,
   but cannot be labelled as, or substitute for, the acknowledgement;
2. ordered monitor heartbeats covering the full active session at no more than
   60-second gaps;
3. per-symbol `callbacks_received`, `callbacks_enqueued`, and an explicit
   `dropped_callback_count`; and
4. capture evidence with source `xtquant.hktransaction`, a
   `source_events_sha256` bound to the raw export, and an `events_sha256` bound
   to the canonical artifact; the accompanying Vault/Beast manifest must carry
   the Vault dataset ID/version/content hash, Beast script/full commit/config
   hash, and cross-check the source export hash; and
5. a reviewed side-verification artifact with `verified=true`, a timezone-aware
   `verified_at`, non-empty `evidence`, and convention
   `xtquant_vendor_doc_dir_1_sell_2_buy`.

Only after those artifacts and the resulting tape, callback-arrival, L2-input,
and L2-coverage quality gates pass can a fresh Vault/Beast artifact be
evaluated beyond `--quality-only`. The 2026-01-08 archive must remain
`BLOCKED_FOR_EMPIRICAL_CLAIMS`.

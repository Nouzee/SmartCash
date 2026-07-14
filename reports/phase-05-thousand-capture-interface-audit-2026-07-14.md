# Phase 5 — Thousand prospective-capture interface audit

Run date: 2026-07-14 (Asia/Shanghai)

Scope: read-only audit of `/home/zrliu/thousand` against SmartCash's required
prospective evidence: a provider acknowledgement per `symbol × period`, durable
heartbeats, callback outcome counters, and raw `hktransaction` plus
`l2thousand` persistence.

## Decision

**Thousand has useful capture building blocks, but no existing interface can
truthfully pass SmartCash's provider-ACK gate.**  The closest implementation,
the dedicated SmartCash capture command, deliberately emits candidate-only
evidence with `subscription_acknowledged=false`.  It also aggregates its
evidence by symbol rather than `symbol × period`.

The required inputs are technically reachable from the local XTQuant client:
native `hktransaction` callbacks, a documented native `l2thousand` callback
interface, callback counters, a raw JSONL writer, and a status/health file.
They are not yet one durable, period-specific capture envelope.  In
particular, no local source provides a provider-issued ACK ID, success state,
and timestamp for either subscription.

## Interface matrix

| Requirement | What exists in Thousand | Durable / `symbol × period`? | SmartCash gate status |
| --- | --- | --- | --- |
| Provider subscription confirmation | `XtQuantMarketDataClient.subscribe()` retains the SDK return in `subscription_handles[(symbol, period)]` and only then records the local symbol as subscribed.  The subprocess sends its own `{type: "subscribed"}` reply after that call. | **No.** Both are local process observations; neither is persisted as a provider receipt. The subprocess reply is per symbol, not per period. | **Cannot satisfy ACK gate.** |
| `hktransaction` acquisition | Generic `subscribe_quote` path wraps callbacks with `{symbol, period, data}`. | Live callback carries both dimensions; raw capture command fsyncs each callback row. | Usable substrate, subject to an external ACK source. |
| `l2thousand` acquisition | Vendored vendor guide documents the dedicated `subscribe_l2thousand(symbol, callback, gear_num)` interface. | **Not wired in the current generic client.** The SmartCash command passes `l2thousand` to the generic `subscribe_quote` client instead. | Current path does not demonstrate the vendor-documented L2 subscription; do not qualify a session from it. |
| Callback received/enqueued/rejected/dropped counters | Client holds aggregate received/enqueued/rejected counters.  SmartCash recorder records received/enqueued/dropped.  Runtime v3's acquisition plane also counts received/enqueued/rejected/dropped. | **No** for the client and v3 status: counters are aggregate, in-memory/health diagnostics, not bound to `symbol × period`. SmartCash's final envelope is symbol-only. | Diagnostic only. |
| Heartbeats | SmartCash command records heartbeats at at most 60 seconds; runtime v3 rewrites health JSON every tick. | SmartCash heartbeat list is held in memory and only written at `finalize`; a crash loses it. It is copied to every symbol but not period-specific. Runtime health is durable but is not a capture heartbeat ledger. | Partial only; not a crash-resilient full-session capture envelope. |
| Raw trade + L2 persistence/export | SmartCash recorder writes fsynced callback JSONL and binds its SHA-256 into final evidence. Runtime v3 records normalized raw callbacks before its state plane and can spool JSONL or publish Kafka; a raw-to-Parquet CLI exists. | SmartCash callback file is durable per event but needs the native L2 adapter and complete envelope. v3 spool is raw-event durable-at-file level but does not fsync each append and has no SmartCash capture evidence. | SmartCash recorder is the appropriate export boundary; v3 is supporting operational evidence only. |
| Status endpoint/CLI/export | `python -m tools.smartcash_live_capture` outputs candidate paths and explicitly states `provider_acknowledgement_recorded=false`, `empirical_claims_allowed=false`. Runtime v3 writes `runtime-health.json`; `runtime_v3_raw_to_parquet` reads raw spool files. | CLI/status outputs are durable only when their files are retained; they do not prove provider ACK or full period coverage. | Useful operations tooling, not gate evidence. |

## Primary-source evidence

### 1. The present SmartCash command correctly refuses to make an ACK claim

The command limits itself to `hktransaction` and `l2thousand`, records a
subscription *return* after `client.subscribe(symbol)`, and starts heartbeats:
[`smartcash_live_capture.py`](/home/zrliu/thousand/backend/tools/smartcash_live_capture.py:23),
[`smartcash_live_capture.py`](/home/zrliu/thousand/backend/tools/smartcash_live_capture.py:44).
Its terminal payload explicitly says no provider acknowledgement was recorded
and empirical claims are disallowed:
[`smartcash_live_capture.py`](/home/zrliu/thousand/backend/tools/smartcash_live_capture.py:123).

The recorder's `record_provider_acknowledgement` raises unless a real adapter
is supplied:
[`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:91).
Its evidence is indexed only by symbol and a `_SymbolCapture` holds one
subscription timestamp and one set of counters for both streams:
[`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:33),
[`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:161).
Thus, even after an ACK source exists, this schema must be expanded to a
`symbol × period` key before it can prove both subscriptions independently.

The raw callback writer itself is strong partial machinery: it writes each row,
flushes and calls `fsync`, then produces an SHA-256-bound evidence file:
[`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:104),
[`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:155).
But heartbeats are accumulated in memory and persisted only during finalization:
[`live_capture.py`](/home/zrliu/thousand/backend/beast_tools/smartcash/live_capture.py:140).

### 2. Current L2 subscription wiring is not the documented native path

The local vendor guide lists `hktransaction` among generic
`subscribe_quote(..., period=...)` streams:
[`xtquant-hk-l2-native-v3.9.md`](/home/zrliu/thousand/docs/xtquant-hk-l2-native-v3.9.md:18).
For thousand-level L2, it instead states that the data are obtained via
`subscribe_l2thousand` and provides that call's signature:
[`xtquant-hk-l2-native-v3.9.md`](/home/zrliu/thousand/docs/xtquant-hk-l2-native-v3.9.md:735).

In contrast, the generic client always dispatches every configured period to
`xtdata.subscribe_quote`:
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:145),
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:375).
The SmartCash CLI constructs that generic client with both periods:
[`smartcash_live_capture.py`](/home/zrliu/thousand/backend/tools/smartcash_live_capture.py:111).
Therefore a capture claiming native `l2thousand` has not been demonstrated by
the documented interface. This is an implementation gap, not evidence that a
generic period string happens to be accepted by a particular SDK build.

### 3. Existing counters and runtime health are operational, not provider proof

The generic client tracks handles in memory and exposes an aggregate stats
snapshot, including all subscribed symbols and configured periods:
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:99),
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:313).
Its callback increments aggregate received/enqueued/rejected counters:
[`xtquant_client.py`](/home/zrliu/thousand/backend/beast_market/xtquant_client.py:390).
The subprocess' `subscribed` JSON line is emitted only after that same local
call, so it is a worker acknowledgement—not an upstream provider receipt:
[`xtquant_subprocess_adapter.py`](/home/zrliu/thousand/backend/beast_market/xtquant_subprocess_adapter.py:478).

Runtime v3 separately measures received/enqueued/rejected/dropped callbacks,
including a bounded queue-full drop path:
[`planes.py`](/home/zrliu/thousand/backend/beast_market/v3/planes.py:54),
[`planes.py`](/home/zrliu/thousand/backend/beast_market/v3/planes.py:82).
It writes a health snapshot at startup and during every runtime tick:
[`production_runtime.py`](/home/zrliu/thousand/backend/beast_market/v3/production_runtime.py:1238).
Those measurements are valuable session diagnostics, but are neither
per-period counters nor an independent provider response.

### 4. Raw-event paths exist, but v3 cannot be substituted for the capture envelope

V3's raw-event recorder runs before the state plane and can send records to a
raw spool and Kafka:
[`persistence.py`](/home/zrliu/thousand/backend/beast_market/v3/persistence.py:349),
[`production_runtime.py`](/home/zrliu/thousand/backend/beast_market/v3/production_runtime.py:1357).
Its spool paths are conventional JSONL append operations without a per-append
`fsync`:
[`persistence.py`](/home/zrliu/thousand/backend/beast_market/v3/persistence.py:496),
[`persistence.py`](/home/zrliu/thousand/backend/beast_market/v3/persistence.py:553).
The export tool can consume these records from
`{runtime_state_root}/{trade_date}/spool/raw_market_events.jsonl` and write
bronze/silver parquet:
[`runtime_v3_raw_to_parquet.py`](/home/zrliu/thousand/backend/tools/runtime_v3_raw_to_parquet.py:41).

However, v3 chooses only one in-process period (`periods[0]`) and routes it
through generic `subscribe_quote`:
[`production_runtime.py`](/home/zrliu/thousand/backend/beast_market/v3/production_runtime.py:1573),
[`acquisition.py`](/home/zrliu/thousand/backend/beast_market/v3/acquisition.py:203).
It consequently does not establish paired native `hktransaction` and
`l2thousand` capture, and its health/spool artifacts contain no provider ACK
or capture-evidence hash chain.

## Recommended integration path

1. Keep `tools.smartcash_live_capture` as the SmartCash-specific boundary;
   do not use gateway `subscribe_ack`, subprocess `subscribed`, a positive SDK
   handle, connection state, or first data callback as provider ACK.
2. Add a narrow acquisition adapter that calls generic `subscribe_quote` for
   `hktransaction` and the documented `subscribe_l2thousand` for L2. Persist
   a stream identity for every `symbol × {hktransaction,l2thousand}`.
3. Change the capture evidence schema to stream-level subscription returns,
   provider receipts, heartbeats, received/enqueued/rejected/dropped counters,
   and a receipt hash. Append/fsync a heartbeat/counter journal throughout the
   session; retain final SHA-256 binding for the event file and journal.
4. Obtain a provider-controlled, durable per-stream ACK feed or audit export
   carrying requested symbol, period, success/failure, provider time, and a
   stable receipt/event ID. Validate and persist its raw bytes before setting
   `subscription_acknowledged=true` for that stream.
5. Feed the resulting event JSONL plus capture envelope through the existing
   Vault/Beast transform and SmartCash `--quality-only` gate. Only a complete
   stream-level ACK/heartbeat/counter envelope that passes the existing quality
   checks may be considered for empirical analysis.

Until step 4 is complete, the truthful state remains
`BLOCKED_FOR_EMPIRICAL_CLAIMS`.

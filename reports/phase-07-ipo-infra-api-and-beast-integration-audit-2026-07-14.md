# Phase 7 — `Detachm/ipo_infra` API and Beast integration audit

Run date: 2026-07-14 (Asia/Shanghai)
Source revision audited: [`de6b192`](https://github.com/Detachm/ipo_infra/tree/de6b1923c0bff115488cea9c96c67257b4cf2f7b)

## Decision

**`ipo_infra` does not unblock SmartCash empirical claims.**  It is a useful
IPO-oriented, historical-data foundation and can supply or normalize
`hktransaction` history, but it exposes no live paired
`hktransaction × l2thousand` capture interface and no provider-controlled
per-stream receipt, durable heartbeat ledger, or stream-level delivery
counters.  It must therefore remain outside SmartCash's accepted empirical
input set.

The correct disposition is:

- use it, if desired, as a **separate historical/IPO research input**;
- keep the SmartCash provider-ACK, heartbeat, and callback-counter fields
  empty for any material derived from it; and
- do not run quality-passing SmartCash analysis, backtests, or alpha claims
  from these outputs.

This is an interface/lineage assessment, not a finding that its historical
data are invalid for its stated IPO purpose.

## What the repository actually exposes

### Query interface: a local Python/Parquet reader, not a network API

The public interface is `IpoDataStore`, with `get_stock(symbol)` and
`get_by_period(start, end)`.  The README explicitly says those calls read
already-generated `silver/` and `gold/` Parquet only; they do not call a
network source at query time.  See the [README query
contract](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/README.md#L5-L21)
and the [implementation's local data directory and
loader](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/ipo_strategy/api.py#L18-L20).

No HTTP, WebSocket, FastAPI, or RPC endpoint is present in the audited tree.
Its Docker service invokes a daily scheduler/pipeline rather than an API
server, as shown in [docker-compose.yml](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docker-compose.yml#L1-L34).

### Available schemas/data products

The intended data model includes IPO master data, HKEX document provenance,
dark-market observations, candidate-pool fields, and an L2 *coverage* view.
The public API's declared columns are visible in
[`ipo_strategy/api.py`](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/ipo_strategy/api.py#L22-L87),
and it pivots `silver/l2_coverage.parquet` into only
`*_coverage_status`, `*_row_count`, `*_available_start`, and
`*_available_end` fields
([loader](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/ipo_strategy/api.py#L250-L270)).

Its design document specifies the raw/batch audit fields `source`, source
URL/file, `fetched_at`, `source_updated_at`, `raw_hash`, and `run_id`
([architecture](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docs/data_architecture.md#L16-L29)).
Those are valuable historical provenance fields, but they are not a live
subscription receipt.

For L2, `silver/l2_coverage` is keyed by `instrument_id`, `data_type`, and a
required time range, with coverage dates, row count, status, missing reason,
and probe time
([schema](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docs/data_architecture.md#L308-L326)).
It reports availability after the fact; it contains none of the SmartCash
capture-evidence fields.

## SmartCash requirement matrix

| Requirement | Evidence in `ipo_infra` | Result |
| --- | --- | --- |
| Historical `hktransaction` | `backfill_xtquant_auction_ticks.py` selects `PERIOD = "hktransaction"`, downloads history, reads it through `get_market_data_ex`, and writes a per-symbol Parquet partition. [Source](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/backfill_xtquant_auction_ticks.py#L1-L8), [fetch](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/backfill_xtquant_auction_ticks.py#L121-L192). | **Available as historical/batch input.** It is specifically an IPO listing-day 09:00–09:30 extraction, not a general live stream. |
| Native `l2thousand` | A full repository scan finds no `subscribe_l2thousand` or `l2thousand` identifier. The documented L2 material is coverage plus historical `trade_tick`/`hkorder`/`hkorderaux`; its own architecture says complete pre-open order book/broker queue remains to be verified by a future real-time probe. [Scope and limitation](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docs/data_architecture.md#L260-L287), [current limitation](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docs/data_architecture.md#L406-L418). | **Not provided.** No paired native stream. |
| Provider ACK/receipt per `symbol × period` | No subscription API exists; neither public schema nor scripts define provider outcome, provider timestamp, stable receipt/event ID, or the requested period. | **Absent.** A batch run ID/raw hash is not an upstream subscription receipt. |
| Durable stream heartbeats | No `heartbeat` implementation or schema exists in the audited source. The daily scheduler is a process schedule, not a capture heartbeat. [Service command](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docker-compose.yml#L19-L34). | **Absent.** |
| received/enqueued/rejected/dropped counters | No such delivery outcome counters exist in the source tree or `l2_coverage` schema. `row_count` measures historical material availability only. | **Absent.** |

## Authentication, runtime, and rate constraints

The XTQuant backfill path launches a local datacenter, optionally takes a token
from `XTQUANT_TOKEN` or a config file, configures a data-home directory, then
connects to `127.0.0.1:<port>`.  It requires an ABI-matched SDK; the README
calls out a Python 3.12 extension in the current deployment.
([startup code](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/backfill_xtquant_daily_gaps.py#L96-L139),
[runtime note](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/README.md#L89-L102)).

For the auction backfill, retries default to three with a two-second sleep;
these are client retry settings, not an advertised provider rate limit.
([arguments](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/backfill_xtquant_auction_ticks.py#L199-L214)).
The repository contains no documented vendor quota, entitlement, or maximum
subscription count.  Any live use must therefore be separately approved and
validated against the actual XTQuant account/provider terms.

The only other explicit external credential is for optional IPO-PDF LLM
extraction: `OPENAI_API_KEY` or `DASHSCOPE_API_KEY`, with a DashScope-compatible
base URL and a default 90-second timeout.  It does not authenticate the local
Parquet query interface or provide market data
([key selection](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/automate_ipo_documents.py#L266-L269),
[client construction](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/automate_ipo_documents.py#L349-L375)).
The HKEX collector has three attempts with 30-second timeout and incremental
2/4-second waits, while the AASTOCKS dark-market loop pauses 0.1 seconds per
symbol.  These are scraper-side retry/throttling settings, not market-stream
entitlements, ACKs, or a documented provider quota
([HKEX request policy](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/fetch_hkex_ipo_sources.py#L29-L40),
[dark-market pacing](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/scripts/scrape_dark_market.py#L216-L242)).

## Relationship to `/home/hliu/beast`

The source was designed to reuse Beast artifacts: its container mounts
`/home/hliu/beast/reports/ipo_research` read-only
([compose integration](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docker-compose.yml#L14-L18)),
and its architecture records Beast's IPO L2 Parquet as a historical asset
([architecture](https://github.com/Detachm/ipo_infra/blob/de6b1923c0bff115488cea9c96c67257b4cf2f7b/docs/data_architecture.md#L395-L419)).

Local inspection confirms Beast's downloader can call XTQuant for historical
`hktransaction`, `hkorder`, and `hkorderaux` and write Parquet batches.  It is
compatible with `ipo_infra` as a producer of historical input, but it is not a
SmartCash live-capture replacement.  In particular, its existing historical
ingestion code does not yield native `l2thousand` paired callbacks or an
upstream receipt/counter/heartbeat envelope.

Safe integration boundary, if historical IPO research is wanted:

1. Run the Beast downloader into a distinct immutable raw/bronze location;
   retain its source path, run ID, hash, time range, and batch manifest.
2. Let `ipo_infra` consume/normalize that batch only into its IPO tables and
   coverage view.
3. Do **not** feed that batch to SmartCash's empirical quality gate.  Mark
   SmartCash's provider ACK, paired native L2, heartbeat, and stream counters
   as unavailable.
4. Keep prospective SmartCash capture on its dedicated native-L2 collector;
   only a provider-controlled receipt adapter plus durable stream journal can
   change the empirical gate.

## Final gate status

`BLOCKED_FOR_EMPIRICAL_CLAIMS` remains the only defensible SmartCash status.
`ipo_infra` narrows the historical-IPO data integration path but supplies none
of the missing live capture evidence and does not provide native
`l2thousand` alongside `hktransaction`.

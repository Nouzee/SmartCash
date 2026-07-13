# Phase 0 — HK Microstructure Data Acceptance

Date: 2026-07-13 (Asia/Shanghai)

## Decision

Phase 0 has started, but real-factor estimation remains blocked. The workspace does not currently contain a complete Hong Kong `hktransaction + l2thousand` event set that can pass the project contract. Synthetic replay remains a wiring test only.

## Evidence collected

- `/home/zrliu/thousand-ccass/backend/beast_market/xtquant_client.py` defines the default live periods as `1m`, `hktransaction`, and `hkbrokerqueueex`; `l2thousand` is not in that default set.
- A workspace file inventory found no persisted Hong Kong file named for `hktransaction` or `l2thousand`. Existing Parquet files belong to Hitchhike reports or Hephaestus A-share/BTC experiments and are not admissible substitutes.
- At 2026-07-13 14:21 Asia/Shanghai, local port 58628 was listening, but the Thousand Runtime at `127.0.0.1:9020/readyz` returned HTTP 503 with `runtime_state=DEGRADED`. Its cache covered 13/13 monitored symbols, but lifecycle readiness failed.
- The existing Runtime can normalize an `l2thousand` callback, but current default acquisition does not prove that full-depth data is subscribed and persisted.
- Broker queue, CCASS and offline Silver are explicitly inadmissible as replacements for missing live trades or full-depth order books.

## Phase 0 implementation — first acceptance tranche

The real replay CLI now writes `data_quality_report.csv`, one row per symbol, with:

- trade and book counts;
- original-file trade and L2 ordering, duplicate trade IDs and trade sequence gaps;
- per-symbol trade subscription ACK, capture start/end heartbeats, maximum active heartbeat gap and dropped-callback count;
- first/last event time and maximum L2 gap;
- requested session end, active-session duration and trailing L2 coverage;
- separate trade/L2 callback-arrival coverage, negative latency, callback ordering, latency maxima and stale-event counts;
- rejected crossed/locked and other invalid L2 snapshots;
- directional and neutral turnover;
- active-broker disclosure coverage;
- active-seat disclosure and broker-entity mapping coverage;
- an explicit failed row for every expected symbol, including symbols with zero accepted events;
- tape, book and combined completeness;
- source and direction-contract provenance.

`coverage_complete` is accepted only when every expected symbol passes tape fragment integrity, an independent full-session trade capture envelope, callback arrival, input validity/staleness and first/intermediate/trailing L2 coverage. Sequence continuity inside a fragment is not accepted as proof that the trade prefix or suffix exists. The capture envelope is SHA-256-bound to the raw event JSONL and requires a subscription ACK before open, raw monitor heartbeats through close with no active gap above 60 seconds, and zero reported dropped callbacks.

The 5-second maximum active-session L2 gap and 1,000-millisecond maximum callback latency are hard upper bounds and cannot be enlarged by a caller. The frozen 2025–2026 HKEX calendar rejects weekends and every exchange-published market holiday, requires Hong Kong `+08:00`, and distinguishes 19,800 active seconds on a full day from 9,000 on the published half days. The scheduled 12:00–13:00 lunch break is excluded from gap time. Sorting for deterministic replay no longer erases raw-order audit results.

Calendar evidence is pinned to the official [HKEX securities trading-hours table](https://www.hkex.com.hk/Services/Trading-hours-and-Severe-Weather-Arrangements/Trading-Hours/Securities-Market?sc_lang=en), the [2025 securities holiday schedule](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2024/ce_SEHK_CT_063_2024.pdf), and the [2026 securities holiday schedule](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf). Dates outside those two calendar years are rejected until the table is deliberately extended from a new exchange publication.

Feature and future-label generation now hard-rejects any session without full capture evidence, complete coverage and an auditable side-verification artifact confirming the selected direction convention. Before all gates pass, `--quality-only` is the only valid real-data mode.

Every invocation requires a new or empty output directory. This prevents a failed or quality-only run from coexisting with stale feature, label, summary or shock artifacts from an earlier successful session. The dropped-callback field is accepted only as a non-boolean, nonnegative JSON integer, so fractional values cannot be truncated into a false zero.

## Unblock requirements

1. Start a separate research capture from market open for a small liquid universe, initially `00700.HK`, `00939.HK`, `02723.HK`, and `06715.HK`.
2. Subscribe and persist raw `hktransaction` and raw `l2thousand` together, retaining exchange timestamp, callback arrival timestamp, sequence/trade ID and source contract; the capture adapter must also persist subscription ACK, monitor heartbeats and dropped-callback counters as a separate evidence artifact.
3. Do not route `hkbrokerqueueex` into this capture's trade or L2 tables.
4. Collect at least ten complete sessions before fitting score weights.
5. First publish daily quality reports; only sessions passing the hard gates may enter feature/label generation.

## Current research status

Status: `BLOCKED_FOR_EMPIRICAL_CLAIMS`, not blocked for engineering.

The next engineering tracer is a standalone raw capture/export adapter. It must not change the production webpage and must not label a partial afternoon capture as a complete day.

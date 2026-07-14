# Phase 0 — HK Microstructure Data Acceptance

Date: 2026-07-13 (Asia/Shanghai)

## Decision

Phase 0 has started, but real-factor estimation remains blocked. The user has fixed Vault as the research data source and Beast as the data-processing script owner. A follow-up inventory on 2026-07-14 found the Vault mount and persisted Hong Kong `hktransaction + l2thousand` data; the initial no-data conclusion below is superseded by the correction in the next section. Synthetic replay remains a wiring test only.

## 2026-07-14 correction — Vault data found

- The authoritative mount is `/vault/core/data`; mentor-owned Beast code is under `/home/hliu/beast`.
- Persisted Octopus-Live realtime files exist under `/vault/core/data/Octopus-Live/PROD/<YYYYMMDD>/realtime`, including sessions 2026-01-06 through 2026-01-09. The 2026-01-08 session contains broad trade and L2 coverage.
- A Beast-owned exporter now selects `tick_archiver` and `l2thousand_enhancer`, preserves their raw PascalCase payloads, and explicitly ignores `large_trade_monitor` broker-queue files.
- The first quality-only replay used 2026-01-08 `00700.HK`: 10,717 trades and 12,275 raw L2 snapshots were exported; SmartCash accepted 12,271 books and rejected four crossed/locked snapshots.
- The persisted files do not include an independent subscription ACK, callback heartbeat envelope, or dropped-callback counter. Filesystem `mtime_ns` is therefore used only as a labelled save-time/arrival proxy, never as proof of complete live capture.
- The session fails empirical gates: 10,715 sequence discontinuities, 3,191 stale trades, 1,445 stale books, a 593.451-second maximum active-session L2 gap, no independent direction verification, zero broker-entity mapping in the replay, and only 0.0267% turnover-weighted active-seat disclosure. A static Mammoth broker mapping exists and covers the sole disclosed seat, but it has not yet been converted into an as-of SmartCash identity artifact.

The detailed run is recorded in [the 2026-01-08 Vault quality report](phase-02-vault-quality-2026-01-08-00700.md).

## Evidence collected

- `/home/zrliu/thousand-ccass/backend/beast_market/xtquant_client.py` defines the default live periods as `1m`, `hktransaction`, and `hkbrokerqueueex`; `l2thousand` is not in that default set.
- The initial `/home/zrliu`-only inventory found no persisted Hong Kong file named for `hktransaction` or `l2thousand`; it did not cover `/vault/core/data` and must not be interpreted as a global no-data finding.
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

1. Capture or locate independent subscription ACK, monitor heartbeat and dropped-callback evidence for a complete session; file save times are insufficient.
2. Independently verify the XTQuant `Dir` convention used by this dataset.
3. Version the candidate `/vault/core/data/Mammoth-v1/silver/base/broker_info/broker_id_to_participant_id.csv` as an as-of SmartCash identity artifact; active-seat disclosure is already measured and remains only 0.0267% by turnover in this sample.
4. Emit the versioned Vault/Beast lineage manifest; continue excluding `hkbrokerqueueex` and `large_trade_monitor` from the trade/L2 artifact.
5. Collect at least ten complete sessions before fitting score weights.
6. First publish daily quality reports; only sessions passing the hard gates may enter feature/label generation.

## Current research status

Status: `BLOCKED_FOR_EMPIRICAL_CLAIMS`, not blocked for engineering.

The next research tracer is to search Vault and mentor capture infrastructure for the missing full-session capture evidence and direction proof. The next engineering tracer is to bind an admissible export to the existing Vault/Beast lineage manifest. Neither may label a saved-file archive as a proven complete live capture.

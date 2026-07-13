# Smart Money Microstructure Prototype Report

Date: 2026-07-13

## Outcome

An independent high-frequency research project now exists at `/home/zrliu/smartcash`. It is event-driven, uses XTQuant `hktransaction` plus `l2thousand`, and keeps realtime features separate from future outcomes.

The prototype includes:

- explicit raw direction convention and active/passive broker separation;
- SmartCash-owned as-of seat/broker-entity mapping with full/display names, external aliases, and historical skill prior;
- L1/L2/L5 imbalance, microprice, OFI, spread/depth, volatility, update activity and recovery proxies;
- 10/30/60/300-second active identity flow;
- confirmed/absorption/conflict/neutral flow-price states;
- causal SmartMoneyScore and completeness/confidence gate;
- ex-ante shock detection and ex-post persistent/dampened/reversed labels;
- post-shock path reversal, signed-flow persistence and flow-decay diagnostics;
- deterministic event replay and 10/30/60/300-second markout labels;
- dual-plane decision/execution snapshots governed by arrival time;
- candidate confirmation, expiry, shock-cluster deduplication and re-arm lifecycle;
- taker-only price-protected IOC fills against the first eligible new L2 snapshot;
- date-aligned 60/1/20/1/20 walk-forward fold construction;
- versioned Lemnis public-order payloads and hash-bound 1s/5s Parquet sidecars;
- explicit 60/300-second warm-up, L2 gap validation and fixed-horizon endpoint tolerance;
- per-symbol Phase 0 tape/L2/identity coverage reports for real replays;
- a hard pre-feature gate requiring expected-universe completeness, callback provenance, the HKEX session calendar and independently verified trade direction;
- synthetic and real-JSONL replay commands.

## Synthetic sanity result

The checked output under `artifacts/demo` uses deterministic synthetic data. Its manifest says `empirical_claims_allowed=false`. It generated:

- 74 frozen feature rows;
- 296 markout labels;
- 1 detected project-defined shock and 1 matured shock outcome after applying a 5bp absolute return floor.

For `trade_eligible` synthetic rows, mean signed midpoint markout was approximately:

| Horizon | Signals | Mean signed markout | Hit rate |
| ---: | ---: | ---: | ---: |
| 10s | 25 | 3.15 bp | 100.0% |
| 30s | 25 | 9.44 bp | 100.0% |
| 60s | 25 | 18.88 bp | 100.0% |
| 300s | 25 | 94.40 bp | 100.0% |

The smaller eligible set now also requires a complete 300-second warm-up. The table validates sign conventions, replay wiring and label separation only. The generator deliberately creates directional paths, so these values and hit rates are not evidence of alpha and must not be presented as real Hong Kong performance.

## Most important empirical blockers

1. The XTQuant direction description and current Thousand exporter disagree. Resolve against an independent source before using signed flow.
2. Thousand currently defaults to `hktransaction` and broker queue, not historical `l2thousand`; full-depth persistence is required.
3. `activeBrokerNo` coverage must be measured. Passive broker fallback would invalidate identity flow.
4. Snapshot-derived refill is only a proxy. True cancellation/addition requires `hkorder` or a reliable incremental order-book feed.
5. Broker skill must be trained on earlier matured markouts with shrinkage and as-of versioning.
6. Protected IOC displayed-book fills now exist, but point-in-time fees, latency scenarios, unobserved impact stress and a portfolio ledger remain absent. Markout is still not net strategy PnL.

Phase 0 inventory on 2026-07-13 found no admissible persisted Hong Kong `hktransaction + l2thousand` dataset in the workspace. Thousand's default live period set also omits `l2thousand`; see [the data acceptance report](phase-00-data-acceptance-2026-07-13.md).

## Framework decision

- Thousand is the acquisition and immutable-event source.
- This project is the tick/L2 feature and label layer.
- SmartCash now writes versioned, hash-bound dual-plane Parquet sidecars and public Lemnis order-batch payloads. Lemnis may provide scheduling, order lifecycle, risk, ledger and replay, while SmartCash remains the L2 execution authority. Local public-object materialization is not yet environment-verified because the Lemnis checkout's declared `polars` dependency is absent.
- Hephaestus can provide assumption/evidence registries, decision gates and reports. Its queue simulator and learned regimes are not validation truth.

## Next real-data run

Start with 00700.HK plus several liquid HK names for at least 10 complete sessions. First publish a data-quality report, then frozen feature/label tables, then component ablations. Do not fit weights until direction, coverage, time ordering and replay equality all pass.

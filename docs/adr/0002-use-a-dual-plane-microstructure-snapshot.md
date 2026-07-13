# Use a dual-plane microstructure snapshot

`MicrostructureStepSnapshot` carries both `decision_state` and `execution_state` under one symbol, as-of time, schema version, completeness state, and source watermark. The decision plane contains causal features and quality gates; the execution plane contains contemporaneously visible L2 prices and sizes, spread, recent trade state, and event positions needed by Lemnis. This avoids a second order-book reconstruction while allowing signal generation and fill simulation to be audited separately.

## Consequences

- Lemnis execution code must not read decision features when determining market liquidity, fillability, price, or queue state.
- Future markouts and shock outcomes never appear in either realtime plane; they remain separate research labels.
- A feature-only export is a projection of the canonical snapshot, not a substitute for the execution contract.
- Every consumer rejects unknown incompatible schema versions or mismatched decision/execution watermarks.

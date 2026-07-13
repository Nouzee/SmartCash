# Separate market-event steps from decision checkpoints

The canonical SmartCash state machine advances after every normalized `hktransaction` or `l2thousand` event, while strategies may create new intents only at deterministic decision checkpoints. The first research cadence is one second; 200ms and 5s are configurable projections, not alternative market clocks. A checkpoint carries forward only the last state known at or before its boundary and must never use an end-of-bin aggregate containing later events.

## Consequences

- Lemnis execution simulation can advance on every market event even when the strategy does not run.
- Repeated checkpoints without new events retain explicit source watermarks and staleness rather than inventing activity.
- Historical and live checkpoint generation must produce identical snapshots for the same ordered input prefix.
- Cadence comparisons change the decision schedule only; they do not change event ordering or reconstruct separate books.

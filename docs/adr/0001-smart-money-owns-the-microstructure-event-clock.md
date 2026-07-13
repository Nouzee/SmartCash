# SmartCash owns the microstructure event clock

SmartCash owns raw `hktransaction`/`l2thousand` event-time advancement, causal order-book reconstruction, and immutable `MicrostructureStepSnapshot` production. SmartCash may compose Lemnis public components for signal-to-intent, orders, risk, execution simulation, ledger, and replay, but Lemnis must not reinterpret raw ticks or become a second source of book state. This boundary preserves one causal microstructure truth while reusing Lemnis infrastructure.

## Consequences

- Phase 1 integration uses a thin adapter from `MicrostructureStepSnapshot` into Lemnis rather than feeding raw market events into Lemnis.
- Historical replay and live processing must use the same SmartCash state transition semantics.
- A future SmartCash runner may compose Lemnis `PhaseAwareRunner` capabilities, but it must advance the SmartCash engine instead of independently reconstructing the book.

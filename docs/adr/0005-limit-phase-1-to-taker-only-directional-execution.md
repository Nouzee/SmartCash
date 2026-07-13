# Limit Phase 1 to taker-only directional execution

Phase 1 supports only directional, marketable orders that walk contemporaneously visible opposite-side L2 depth after `eligible_from`. Passive orders remain `fill_unknown` and contribute no strategy return because `l2thousand` snapshots and public trades cannot establish queue position or prove our hypothetical fill. Market making is explicitly outside project scope: no two-sided quoting, inventory-skew control, maker rebates, queue-jumping, or spread-capture claims.

## Consequences

- `HkL2ExchangeSimulator` initially accepts marketable IOC-style instructions only and applies taker costs.
- Fill quantity is bounded by visible depth, a configured participation cap, symbol-specific board lot, cash, and available position.
- `hktransaction` remains an order-flow input and audit observation; it is not an order acknowledgment or fill report.
- Maker strategies require a separately approved scope plus `hkorder`-grade events or real order acknowledgments and fills.

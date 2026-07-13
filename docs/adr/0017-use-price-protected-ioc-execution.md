# Use price-protected IOC execution

SmartCash v0 uses taker-only IOC execution against the first eligible, quality-passing L2 snapshot. The worst executable price is bounded by both ten basis points from the decision midpoint and two ticks beyond the contemporaneous best opposite quote, using the stricter bound; only the first five displayed levels are eligible and any remainder cancels immediately.

## Consequences

- If the best opposite quote is already outside the bound, the result is `UNFILLED_PRICE_PROTECTION` rather than a losing trade.
- Fills use actual level-by-level quantities and VWAP; future snapshots, refills, and trade prints cannot complete the IOC.
- Reports include 5bp/10bp/20bp price-protection sensitivity while keeping the two-tick bound explicit.
- Price protection, visible-depth participation, board-lot rounding, cash, and position limits all apply; satisfying one does not bypass another.

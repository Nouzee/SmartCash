# Separate observed sweep, fees, and impact stress

SmartCash decomposes execution cost into three non-overlapping layers: observed sweep cost from level-by-level L2 VWAP versus decision midpoint; point-in-time statutory, clearing, and broker fee items; and a separately reported 0bp/2bp/5bp unobserved-impact stress. Because the L2 VWAP already includes spread crossing and displayed-level slippage, no fixed slippage is added to it.

## Consequences

- Every fill ledger records fee components rather than only aggregate cost basis points.
- Statutory and clearing rates are selected by trade date from official-source effective-date records; broker commission and minimum commission remain account configuration.
- Impact stress is a scenario dimension and cannot be described as observed execution.
- SmartCash extends the simpler Lemnis commission/stamp-tax interface through an adapter without changing historical fees to today's schedule.

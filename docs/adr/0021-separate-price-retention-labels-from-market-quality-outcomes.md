# Separate price-retention labels from market-quality outcomes

SmartCash labels shock sustainability from candidate time `t0` using `retention_h = direction × (mid(t0+h) / pre_shock_mid - 1) / abs(shock_return)`: persistent at or above 0.5, dampened strictly between 0 and 0.5, and reversed at or below 0. Path reversal, spread recovery, depth recovery, signed-flow persistence, and order-flow decay remain separate outcome columns rather than being folded into the primary label.

## Consequences

- Price-retention outcomes are produced at fixed 10s, 30s, 60s, and 300s horizons from `t0`.
- Execution markouts, MAE, and MFE start from actual simulated fill time and price, never from candidate detection or decision midpoint.
- Realtime gates cannot read either outcome family.
- The prototype's existing composite `sustainable_price_discovery` boolean is deprecated for the next implementation phase because it mixes directional persistence with market-quality outcomes.

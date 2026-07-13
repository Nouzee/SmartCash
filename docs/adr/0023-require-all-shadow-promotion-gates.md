# Require all shadow-promotion gates

SmartCash may advance from offline research to non-trading shadow operation only after at least three locked test folds and 200 filled `SmartMoneyConfirmed` episodes, with at least 90% expected symbol-day empirical admissibility and 80% identity coverage at candidates. Under the primary 100ms, HKD 50k/two-percent-depth, 10bp Protected IOC, point-in-time-fee scenario, every test fold must have positive mean 60-second net markout and the date-block-bootstrap aggregate 95% confidence interval must have a lower bound above zero.

## Consequences

- Persistent precision must exceed its unconditional base rate by at least ten percentage points.
- The identity-full model must improve net markout over `MicrostructureConfirmed` and reduce filled negative-net-markout episodes by at least twenty percent.
- The aggregate result must remain non-negative at 250ms latency plus 2bp impact stress.
- No single symbol may contribute more than twenty percent of signal count or PnL.
- All gates are conjunctive; experimental shorts and selectively reported folds cannot satisfy promotion.

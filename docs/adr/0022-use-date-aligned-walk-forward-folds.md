# Use date-aligned walk-forward folds

SmartCash evaluates every rule and model on rolling, market-wide date partitions: sixty trading days of training, one full-day embargo, twenty days of validation, one full-day embargo, and twenty locked test days, advancing twenty days per fold. All symbols from a date remain in the same partition, and at least three test folds are required before promotion.

## Consequences

- Random event splits are prohibited even though the reference Gomber paper used one for its prediction task.
- Shock clusters cannot cross partitions, and outcomes whose fixed 300-second endpoint is incomplete at a boundary are excluded with reason.
- Identity skill priors update after each close using only outcomes matured by that as-of time.
- Validation may choose registered alternatives; opening a test fold permanently locks the corresponding rule/model version for that fold.

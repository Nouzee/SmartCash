# Keep short signals as a non-deployable experiment

SmartCash researches positive and negative shocks symmetrically, but its deployable strategy remains long/flat because live short selling is unavailable. Negative `SmartMoneyConfirmed` events remain a first-class experimental signal: they may drive long exits and may be evaluated in a separately labelled hypothetical short backtest, but they cannot contribute to deployable portfolio performance.

## Consequences

- Deployable results allow buys to open long exposure and sells only to reduce or close it.
- Short research reports directional markouts as the primary result and separates any hypothetical taker P&L that lacks borrow availability, short-sale eligibility, borrow fees, recall risk, or regulatory constraints.
- Deployable and experimental fills, ledgers, Sharpe ratios, and drawdowns are never pooled.
- A short strategy requires a new promotion decision after the missing market and borrow data are available.

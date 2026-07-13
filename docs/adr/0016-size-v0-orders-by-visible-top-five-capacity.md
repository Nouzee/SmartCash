# Size v0 orders by visible top-five capacity

The v0 deployable scenario targets the minimum of HKD 50,000, two percent of contemporaneously visible opposite-side top-five L2 notional after order eligibility, and available cash or sellable position. Quantity rounds down to the symbol's point-in-time HKEX board lot. This is a frozen comparison scenario, not an optimized or guaranteed capacity estimate.

## Consequences

- Reports include HKD 10k/50k/100k target-notional and 1%/2%/5% displayed-depth participation sensitivity curves.
- A result below one board lot is `UNFILLED_CAPACITY`, not a zero-return or losing trade.
- Hidden liquidity, future refill, broker queues, and daily turnover cannot increase visible capacity.
- SmartCash supplies per-symbol board lots through its reference adapter; Lemnis's current single market-wide `trade_unit` cannot govern HK execution.

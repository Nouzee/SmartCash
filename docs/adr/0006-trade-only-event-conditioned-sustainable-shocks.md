# Trade only event-conditioned sustainable shocks

Smart-money computes continuous microstructure features at decision checkpoints but does not trade a raw `SmartMoneyScore`. A candidate event begins only when price, active identity flow, or book liquidity is abnormal relative to its causal history; a separate sustainability gate may then create a directional intent using newly observed flow persistence, price response, liquidity recovery, and identity concentration. This transfers Gomber's persistent-versus-transient reasoning without pretending ordinary HK price moves are Xetra volatility interruptions.

## Consequences

- Continuous score distributions remain research features and ablation inputs, not order triggers.
- Candidate detection, realtime confirmation, and ex-post `persistent/dampened/reversed` labels are separate stages with separate timestamps.
- An absorption candidate enters a research cohort but cannot trade until a future independently validated rule promotes it.
- Every trade must reference the candidate event and the checkpoint at which the sustainability gate first passed.

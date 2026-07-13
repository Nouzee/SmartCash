# Use seasonal robust shock baselines

SmartCash detects abnormal price, signed-flow, OFI, spread, and depth channels against a pre-open profile indexed by symbol and five-minute time-of-day bucket, estimated from the preceding twenty empirically admissible sessions with median and MAD. The v0 abnormal threshold is absolute robust z-score four; a price channel additionally requires absolute return above both five basis points and four times causal trailing-60-second volatility.

## Consequences

- Any one abnormal channel may open a Candidate Shock, but it cannot bypass the Sustainability Gate.
- The first five continuous-trading minutes are warm-up only and cannot produce deployable candidates.
- Reports include 3-MAD/4-MAD/5-MAD sensitivity without changing the frozen test threshold.
- Current-day observations do not refit that day's baseline or retroactively alter candidate history.

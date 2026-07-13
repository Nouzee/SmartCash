# Freeze a point-in-time top-fifty equity universe

For Phase 1, SmartCash freezes each day's pre-open universe to the top fifty ordinary HK equities by median turnover over the preceding twenty complete trading sessions, using only information available before that day's open. Eligible instruments also require point-in-time listing status, board lot, tick size, and calendar/session metadata. ETFs, warrants, CBBCs, bonds, and other product structures remain outside the first model.

## Consequences

- Current-day final turnover, spread, event count, and data availability cannot select that same day's universe.
- Identity mapping does not select the universe; it gates promotion at candidate time.
- Post-session capture failure marks a symbol-day empirically inadmissible with an explicit reason and coverage denominator; it is data-quality censoring, not an alpha rule.
- Product-family expansion requires separate baselines and validation rather than pooling unlike microstructures.

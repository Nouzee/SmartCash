# Cap v0 trade episodes at sixty seconds

The v0 SmartCash strategy closes a directional trade episode no later than sixty seconds after entry. It exits earlier when a causally observed opposite `MicrostructureConfirmed` event appears, sufficiently covered identity flow explicitly conflicts, market/data-quality gates fail, or the session approaches the lunch break or close. Positions do not cross the lunch break or remain overnight.

## Consequences

- Research still reports 10s, 30s, 60s, and 300s markouts, but future horizons cannot select a per-trade exit retrospectively.
- New entries are blocked when the remaining continuous session cannot contain the configured episode and execution buffer.
- Experimental short episodes use the same exit and session-boundary rules as deployable long episodes.
- Alternative holding periods are walk-forward experiments, not silent replacements chosen from test results.

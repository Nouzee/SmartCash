# Require two fresh confirmations within five seconds

A Candidate Shock enters observation at `t0` and cannot trade immediately. Starting at `t0+1s`, its Sustainability Gate must pass at two consecutive one-second decision checkpoints no later than `t0+5s`; the interval must contain both a newly observed directional trade and a newly observed book update, so carried-forward stale state cannot demonstrate persistence. The second passing checkpoint becomes `confirmed_at`, after which normal configured order latency still applies.

## Consequences

- Candidate state transitions are one-way: `detected → observing → confirmed` or `detected → observing → expired`.
- An expired candidate cannot be revived by late events or a later checkpoint; a new anomaly must create a new candidate.
- Reports retain `detected_at`, both confirmation checkpoints, their source watermarks, `confirmed_at`, and any expiry reason.
- Confirmation-window alternatives are registered walk-forward experiments rather than test-set tuning.

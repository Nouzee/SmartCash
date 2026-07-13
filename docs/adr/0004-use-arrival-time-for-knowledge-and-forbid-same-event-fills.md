# Use arrival time for knowledge and forbid same-event fills

Exchange `event_ts` defines market-time semantics and feature windows, but `captured_at` defines when the research system could know an event. A decision checkpoint may consume only events captured by that checkpoint; late events never rewrite an earlier decision. An order becomes executable at `eligible_from = decision_time + configured_latency` and may fill only from a newly arriving market event at or after eligibility, never from the snapshot that generated its signal.

## Consequences

- Replay processes the recorded arrival sequence and retains both event and capture timestamps; sorting by exchange time must not erase latency or callback-order evidence.
- Lemnis maps `eligible_from` onto its existing pending-order lifecycle.
- Zero latency is a diagnostic upper bound, not a headline result; empirical reports include at least 50ms, 100ms, 250ms, and 500ms sensitivity cases.
- Sessions whose arrival disorder or latency exceeds the frozen data-quality gates remain inadmissible for empirical claims.

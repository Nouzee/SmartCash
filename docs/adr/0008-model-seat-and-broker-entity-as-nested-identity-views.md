# Model seat and broker entity as nested identity views

SmartCash preserves raw `activeBrokerNo` as `seat_code` and maps one or more seats as-of to its own stable `broker_entity_id`. Seat-level and broker-entity-level flows are separate diagnostic views of the same trades, not independent evidence that can be added together. Multiple seats belonging to one broker may describe within-broker dispersion but do not count as multiple independent informed entities.

## Consequences

- Every trade contributes once to the final hierarchical identity score even when it appears in both views.
- Missing mappings retain seat evidence but cannot manufacture broker-entity evidence.
- Identity records retain full name, display name, provenance, and effective dates.
- The prototype's current `participant_id` naming must migrate before Lemnis integration; no production code is changed during this specification phase.

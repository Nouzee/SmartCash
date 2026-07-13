# Integrate with Lemnis through a versioned snapshot contract

SmartCash remains independently versioned and exposes `MicrostructureStepSnapshot v1` as its public integration boundary. Historical integration first uses Parquet sidecars plus an immutable manifest; live integration later carries the same fields in event messages. Lemnis is reusable high-frequency infrastructure that SmartCash may depend on through public interfaces, while neither repository imports the other's internal business modules.

## Consequences

- Phase 1 proves the offline sidecar adapter before any production live wiring.
- Contract compatibility is explicit by schema version, and incompatible consumers fail closed.
- SmartCash data-source adapters do not import Thousand or CCASS application modules.
- SmartCash owns the end-to-end product and may reuse Lemnis orchestration, risk, execution, ledger, and replay components without transferring its domain ownership to Lemnis.

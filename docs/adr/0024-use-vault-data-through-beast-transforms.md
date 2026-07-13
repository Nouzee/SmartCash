# Use Vault data through Beast transforms

SmartCash research reads historical/raw market data from Vault. Beast-owned processing scripts transform a pinned Vault dataset into SmartCash's canonical `hktransaction` and `l2thousand` event artifacts. SmartCash owns the factor, lifecycle, execution and label semantics; it consumes versioned artifacts rather than importing Beast business internals or treating Thousand as its default research data API.

## Consequences

- Every accepted artifact carries a fail-closed lineage manifest with Vault dataset ID/version/content hash, Beast script/commit/config hash and output hash.
- Beast must preserve the raw exchange `event_ts` and acquisition `captured_at`; it cannot sort away arrival-order evidence, derive a missing arrival time, infer trade direction from CCASS, or relabel a partial session as complete.
- Both `hktransaction` and `l2thousand` are mandatory. `broker_queue/hkbrokerqueueex` remains inadmissible as either trade or L2 input.
- The Beast transform will be developed and run in its owning tooling repository. SmartCash tests the artifact contract and then performs causal replay.
- The Vault endpoint/mount and a concrete Beast SmartCash transform entry point are environment inputs; neither was discoverable in the current workspace during this implementation turn, so no empirical data claim is unlocked yet.

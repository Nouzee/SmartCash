# Keep SmartCash independent from CCASS ontology

SmartCash is an independent high-frequency microstructure project and owns its contracts, canonical identity keys, feature semantics, and research lifecycle. It may consume verified data or mappings produced elsewhere through explicit adapters, but it does not inherit the CCASS participant ontology, holdings semantics, T+2 timing, rankings, or application interfaces. A CCASS participant ID, when genuinely useful for identity resolution, is stored only as a provenance-bearing external alias.

## Consequences

- No SmartCash factor depends on CCASS holdings or derives realtime direction from CCASS data.
- SmartCash does not import thousand-ccass business modules; adapters consume versioned records or raw source files at the boundary.
- Reused datasets retain source, as-of/effective dates, completeness, and transformation provenance.
- Lemnis integration depends on the SmartCash snapshot contract, not on a CCASS API or UI model.

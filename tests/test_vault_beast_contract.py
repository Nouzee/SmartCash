from smartcash.integrations.vault_beast import (
    VAULT_BEAST_MANIFEST_SCHEMA_VERSION,
    BeastTransformRef,
    VaultBeastArtifactManifest,
    VaultDatasetRef,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def test_vault_beast_manifest_preserves_causal_source_provenance() -> None:
    manifest = VaultBeastArtifactManifest(
        vault=VaultDatasetRef(
            dataset_id="hk-l2-20260713",
            version="v3",
            content_sha256=SHA_A,
        ),
        beast=BeastTransformRef(
            script="beast_tools.smartcash.build_events",
            commit="0123456789abcdef",
            config_sha256=SHA_B,
        ),
        artifact_sha256=SHA_C,
        source_kinds=("hktransaction", "l2thousand"),
        preserves_event_ts=True,
        preserves_captured_at=True,
        broker_queue_used=False,
    )

    payload = manifest.to_dict()

    assert payload["schema_version"] == VAULT_BEAST_MANIFEST_SCHEMA_VERSION
    assert payload["vault"]["dataset_id"] == "hk-l2-20260713"
    assert payload["beast"]["script"] == "beast_tools.smartcash.build_events"
    assert payload["source_kinds"] == ["hktransaction", "l2thousand"]
    assert payload["broker_queue_used"] is False


def test_vault_beast_manifest_fails_closed_when_causality_is_not_proven() -> None:
    base = {
        "vault": VaultDatasetRef("dataset", "v1", SHA_A),
        "beast": BeastTransformRef("beast.transform", "abcdef1", SHA_B),
        "artifact_sha256": SHA_C,
        "source_kinds": ("hktransaction", "l2thousand"),
        "preserves_event_ts": True,
        "preserves_captured_at": True,
        "broker_queue_used": False,
    }

    for override in (
        {"preserves_captured_at": False},
        {"broker_queue_used": True},
        {"source_kinds": ("hktransaction",)},
    ):
        try:
            VaultBeastArtifactManifest(**(base | override))
        except ValueError:
            pass
        else:
            raise AssertionError("inadmissible Vault/Beast lineage must fail closed")

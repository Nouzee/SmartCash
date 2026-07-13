import json

from smartcash.integrations.vault_beast import (
    VAULT_BEAST_MANIFEST_SCHEMA_VERSION,
    BeastTransformRef,
    VaultBeastArtifactManifest,
    VaultDatasetRef,
    load_vault_beast_manifest,
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
            commit="0" * 40,
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
        "beast": BeastTransformRef("beast.transform", "1" * 40, SHA_B),
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


def test_beast_transform_requires_an_immutable_full_commit_digest() -> None:
    try:
        BeastTransformRef("beast.transform", "main", SHA_B)
    except ValueError as error:
        assert "commit" in str(error)
    else:
        raise AssertionError("a mutable branch name cannot identify a Beast transform")


def test_manifest_loader_hash_binds_the_beast_artifact(tmp_path) -> None:
    path = tmp_path / "vault-beast-manifest.json"
    payload = VaultBeastArtifactManifest(
        vault=VaultDatasetRef("dataset", "v1", SHA_A),
        beast=BeastTransformRef("beast.transform", "1" * 40, SHA_B),
        artifact_sha256=SHA_C,
        source_kinds=("hktransaction", "l2thousand"),
        preserves_event_ts=True,
        preserves_captured_at=True,
        broker_queue_used=False,
    ).to_dict()
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_vault_beast_manifest(path, expected_artifact_sha256=SHA_C)

    assert loaded.artifact_sha256 == SHA_C
    try:
        load_vault_beast_manifest(path, expected_artifact_sha256=SHA_B)
    except ValueError as error:
        assert "hash" in str(error)
    else:
        raise AssertionError("lineage must be bound to the exact replay artifact")

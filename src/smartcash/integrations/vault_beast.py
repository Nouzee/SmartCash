"""Fail-closed lineage contract for Vault data transformed by Beast scripts."""

from __future__ import annotations

from dataclasses import dataclass


VAULT_BEAST_MANIFEST_SCHEMA_VERSION = "smartcash.vault-beast.v1"
_REQUIRED_SOURCE_KINDS = frozenset({"hktransaction", "l2thousand"})
_FORBIDDEN_SOURCE_KINDS = frozenset({"broker_queue", "hkbrokerqueueex"})


@dataclass(frozen=True, slots=True)
class VaultDatasetRef:
    dataset_id: str
    version: str
    content_sha256: str

    def __post_init__(self) -> None:
        if not self.dataset_id or not self.version:
            raise ValueError("Vault dataset_id and version are required")
        _require_sha256(self.content_sha256, "Vault content_sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True, slots=True)
class BeastTransformRef:
    script: str
    commit: str
    config_sha256: str

    def __post_init__(self) -> None:
        if not self.script or not self.commit:
            raise ValueError("Beast script and commit are required")
        _require_sha256(self.config_sha256, "Beast config_sha256")

    def to_dict(self) -> dict[str, str]:
        return {
            "script": self.script,
            "commit": self.commit,
            "config_sha256": self.config_sha256,
        }


@dataclass(frozen=True, slots=True)
class VaultBeastArtifactManifest:
    vault: VaultDatasetRef
    beast: BeastTransformRef
    artifact_sha256: str
    source_kinds: tuple[str, ...]
    preserves_event_ts: bool
    preserves_captured_at: bool
    broker_queue_used: bool
    schema_version: str = VAULT_BEAST_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != VAULT_BEAST_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Vault/Beast manifest schema version")
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        kinds = frozenset(self.source_kinds)
        if len(kinds) != len(self.source_kinds):
            raise ValueError("source_kinds must be unique")
        if not _REQUIRED_SOURCE_KINDS.issubset(kinds):
            raise ValueError("Vault/Beast artifact requires hktransaction and l2thousand")
        if kinds & _FORBIDDEN_SOURCE_KINDS or self.broker_queue_used:
            raise ValueError("broker_queue cannot be used by SmartCash data transforms")
        if not self.preserves_event_ts or not self.preserves_captured_at:
            raise ValueError("Vault/Beast artifact must preserve event_ts and captured_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "vault": self.vault.to_dict(),
            "beast": self.beast.to_dict(),
            "artifact_sha256": self.artifact_sha256,
            "source_kinds": list(self.source_kinds),
            "preserves_event_ts": self.preserves_event_ts,
            "preserves_captured_at": self.preserves_captured_at,
            "broker_queue_used": self.broker_queue_used,
        }


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        raise ValueError(f"{label} must be a 64-character hexadecimal digest")

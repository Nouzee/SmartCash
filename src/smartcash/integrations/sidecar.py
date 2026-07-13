"""Immutable Parquet sidecar boundary for offline Lemnis composition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

from ..contracts import MicrostructureStepSnapshot, SNAPSHOT_SCHEMA_VERSION


LEMNIS_SNAPSHOT_SIDECAR_SCHEMA_VERSION = "smartcash.lemnis.snapshot-sidecar.v1"


class MicrostructureSidecarWriter:
    def __init__(self, *, checkpoint_seconds: int) -> None:
        if checkpoint_seconds not in (1, 5):
            raise ValueError("checkpoint_seconds must be 1 or 5")
        self._checkpoint_seconds = checkpoint_seconds

    def write(
        self,
        snapshots: Sequence[MicrostructureStepSnapshot],
        output_dir: Path,
    ) -> dict[str, object]:
        if not snapshots:
            raise ValueError("at least one snapshot is required")
        output_dir = Path(output_dir)
        if output_dir.exists() and any(output_dir.iterdir()):
            raise FileExistsError("sidecar requires a new or empty output directory")
        output_dir.mkdir(parents=True, exist_ok=True)

        if any(snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION for snapshot in snapshots):
            raise ValueError("all snapshots must use the current SmartCash schema")
        if any(
            left.as_of > right.as_of
            for left, right in zip(snapshots, snapshots[1:], strict=False)
        ):
            raise ValueError("snapshots must be ordered by as_of")

        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except (ImportError, ModuleNotFoundError) as error:
            raise RuntimeError("writing a Lemnis sidecar requires the research pyarrow extra") from error

        rows = [self._row(snapshot) for snapshot in snapshots]
        parquet_path = output_dir / "microstructure_steps.parquet"
        pq.write_table(pa.Table.from_pylist(rows), parquet_path, compression="zstd")
        parquet_sha256 = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
        symbols = sorted({snapshot.symbol for snapshot in snapshots})
        manifest: dict[str, object] = {
            "sidecar_schema_version": LEMNIS_SNAPSHOT_SIDECAR_SCHEMA_VERSION,
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
            "dataset_mode": "historical_replay",
            "execution_owner": "smartcash",
            "lemnis_role": "order_lifecycle_risk_ledger_replay",
            "checkpoint_seconds": self._checkpoint_seconds,
            "snapshot_rows": len(snapshots),
            "symbols": symbols,
            "first_as_of": min(snapshot.as_of for snapshot in snapshots).isoformat(),
            "last_as_of": max(snapshot.as_of for snapshot in snapshots).isoformat(),
            "parquet_file": parquet_path.name,
            "parquet_sha256": parquet_sha256,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def _row(snapshot: MicrostructureStepSnapshot) -> dict[str, Any]:
        return {
            "schema_version": snapshot.schema_version,
            "symbol": snapshot.symbol,
            "as_of": snapshot.as_of,
            "complete": snapshot.complete,
            "book_event_ts": snapshot.source_watermark.book_event_ts,
            "book_captured_at": snapshot.source_watermark.book_captured_at,
            "trade_event_ts": snapshot.source_watermark.trade_event_ts,
            "trade_captured_at": snapshot.source_watermark.trade_captured_at,
            "trade_id": snapshot.source_watermark.trade_id,
            "decision_state_json": _canonical_json(snapshot.decision_state),
            "execution_state_json": _canonical_json(snapshot.execution_state),
            "source_watermark_json": _canonical_json(snapshot.source_watermark),
        }


def _canonical_json(value: object) -> str:
    return json.dumps(
        asdict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported sidecar value: {type(value).__name__}")

import hashlib
import json
from datetime import datetime, timedelta

import pyarrow.parquet as pq

from smartcash.contracts import BookLevel, BookSnapshotEvent, SessionContext
from smartcash.engine import SmartCashEngine
from smartcash.integrations.sidecar import (
    LEMNIS_SNAPSHOT_SIDECAR_SCHEMA_VERSION,
    MicrostructureSidecarWriter,
)


BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def _snapshot():
    engine = SmartCashEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=BASE + timedelta(seconds=1),
            captured_at=BASE + timedelta(seconds=1, milliseconds=20),
            bids=(BookLevel(100.0, 1_000),),
            asks=(BookLevel(100.2, 800),),
            source="xtquant.l2thousand",
        )
    )
    return engine.step_snapshot("00700.HK", BASE + timedelta(seconds=2))


def test_sidecar_freezes_dual_plane_snapshots_and_hash_binds_manifest(tmp_path) -> None:
    manifest = MicrostructureSidecarWriter(checkpoint_seconds=1).write((_snapshot(),), tmp_path)

    parquet_path = tmp_path / "microstructure_steps.parquet"
    manifest_path = tmp_path / "manifest.json"
    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    table = pq.read_table(parquet_path).to_pylist()
    execution = json.loads(table[0]["execution_state_json"])

    assert manifest == persisted_manifest
    assert manifest["sidecar_schema_version"] == LEMNIS_SNAPSHOT_SIDECAR_SCHEMA_VERSION
    assert manifest["snapshot_rows"] == 1
    assert manifest["checkpoint_seconds"] == 1
    assert manifest["parquet_sha256"] == hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    assert table[0]["symbol"] == "00700.HK"
    assert execution["bids"][0]["price"] == 100.0
    assert execution["book_captured_at"].endswith("+08:00")


def test_sidecar_refuses_to_mix_with_an_existing_run(tmp_path) -> None:
    writer = MicrostructureSidecarWriter(checkpoint_seconds=5)
    writer.write((_snapshot(),), tmp_path)

    try:
        writer.write((_snapshot(),), tmp_path)
    except FileExistsError as error:
        assert "empty output directory" in str(error)
    else:
        raise AssertionError("sidecar writer must not overwrite a prior run")

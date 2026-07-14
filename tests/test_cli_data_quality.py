import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from smartcash.cli import (
    _positive_milliseconds,
    _prepare_output_dir,
    load_events,
    load_side_verification,
    load_trade_capture_evidence,
    main,
)
from smartcash.integrations.vault_beast import (
    BeastTransformRef,
    VaultBeastArtifactManifest,
    VaultDatasetRef,
)
from smartcash.xtquant import DirectionConvention


def write_jsonl(path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def trade(seq: int, timestamp_ms: int, trade_id: str) -> dict[str, object]:
    return {
        "kind": "hktransaction",
        "symbol": "00700.HK",
        "captured_at": datetime.fromtimestamp(timestamp_ms / 1_000, tz=timezone.utc).isoformat(),
        "payload": {
            "time": timestamp_ms,
            "price": 400.0,
            "volume": 100,
            "dir": 2,
            "activeBrokerNo": 101,
            "brokerNo": 9999,
            "tradeID": trade_id,
            "seq": seq,
        },
    }


def write_archive_lineage(path, events_path, source_snapshot_sha256: str = "a" * 64) -> None:
    """Write the immutable Vault/Beast lineage required for archive replays."""

    artifact_sha256 = hashlib.sha256(events_path.read_bytes()).hexdigest()
    manifest = VaultBeastArtifactManifest(
        vault=VaultDatasetRef(
            dataset_id="octopus-live-prod-20260105",
            version="2026-01-05",
            content_sha256=source_snapshot_sha256,
            export_sha256=artifact_sha256,
        ),
        beast=BeastTransformRef(
            script="beast_tools.smartcash.octopus_live",
            commit="b" * 40,
            config_sha256="c" * 64,
        ),
        artifact_sha256=artifact_sha256,
        source_kinds=("hktransaction", "l2thousand"),
        preserves_event_ts=True,
        preserves_captured_at=True,
        broker_queue_used=False,
        captured_at_sources=("vault_file_mtime_ns",),
    )
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")


def test_tape_audit_detects_file_order_duplicates_and_sequence_gaps(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    write_jsonl(
        path,
        [
            trade(2, 1_767_576_602_000, "duplicate"),
            trade(4, 1_767_576_601_000, "duplicate"),
        ],
    )

    events, audit, _book_audit = load_events(path, DirectionConvention.VENDOR_DOC)

    assert [event.event_ts for event in events] == [
        datetime.fromtimestamp(1_767_576_602, tz=timezone.utc),
        datetime.fromtimestamp(1_767_576_601, tz=timezone.utc),
    ]
    assert [event.captured_at for event in events] == [
        datetime.fromtimestamp(1_767_576_602, tz=timezone.utc),
        datetime.fromtimestamp(1_767_576_601, tz=timezone.utc),
    ]
    assert audit.out_of_order_count == 1
    assert audit.duplicate_trade_id_count == 1
    assert audit.sequence_gap_count == 1
    assert not audit.tape_complete


def test_vault_pascal_case_sequence_is_audited(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    rows = []
    for sequence, timestamp_ms in ((41, 1_767_576_601_000), (42, 1_767_576_602_000)):
        row = trade(sequence, timestamp_ms, str(sequence))
        payload = row["payload"]
        assert isinstance(payload, dict)
        payload["Seq"] = payload.pop("seq")
        payload["TradeID"] = payload.pop("tradeID")
        rows.append(row)
    write_jsonl(path, rows)

    _events, audit, _book_audit = load_events(path, DirectionConvention.VENDOR_DOC)

    assert audit.sequence_present
    assert audit.sequence_gap_count == 0
    assert audit.duplicate_trade_id_count == 0


def test_generic_tick_alias_is_rejected_instead_of_relabelled_as_xtquant(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    row = trade(1, 1_767_576_601_000, "1")
    row["kind"] = "tick"
    write_jsonl(path, [row])

    with pytest.raises(ValueError, match="unsupported event kind"):
        load_events(path, DirectionConvention.VENDOR_DOC)


def test_crossed_book_is_counted_as_rejected_instead_of_disappearing(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    write_jsonl(
        path,
        [
            trade(1, 1_767_576_601_000, "1"),
            {
                "kind": "l2thousand",
                "symbol": "00700.HK",
                "captured_at": "2026-01-05T09:30:01+08:00",
                "payload": {
                    "time": 1_767_576_601_000,
                    "bidPrice": [400.2],
                    "bidVolume": [10_000],
                    "askPrice": [400.0],
                    "askVolume": [8_000],
                },
            },
        ],
    )

    events, _tape_audit, book_audit = load_events(path, DirectionConvention.VENDOR_DOC)

    assert len(events) == 1
    symbol_audit = book_audit.for_symbol("00700.HK")
    assert symbol_audit is not None
    assert symbol_audit.rejected_crossed_locked_count == 1
    assert not symbol_audit.input_complete


def test_real_replay_cli_writes_phase_zero_quality_report(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "output"
    rows = []
    for sequence, timestamp_ms in ((1, 1_767_576_601_000), (2, 1_767_576_602_000)):
        rows.extend(
            (
                trade(sequence, timestamp_ms, str(sequence)),
                {
                    "kind": "l2thousand",
                    "symbol": "00700.HK",
                    "captured_at": datetime.fromtimestamp(timestamp_ms / 1_000, tz=timezone.utc).isoformat(),
                    "payload": {
                        "time": timestamp_ms,
                        "bidPrice": [399.8],
                        "bidVolume": [10_000],
                        "askPrice": [400.0],
                        "askVolume": [8_000],
                    },
                },
            )
        )
    write_jsonl(events_path, rows)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart-money",
            "--events-jsonl",
            str(events_path),
            "--output-dir",
            str(output_dir),
            "--dataset-mode",
            "historical_replay",
            "--direction-convention",
            DirectionConvention.VENDOR_DOC.value,
            "--expected-open",
            "2026-01-05T09:30:00+08:00",
            "--session-start",
            "2026-01-05T09:30:01+08:00",
            "--expected-end",
            "2026-01-05T16:00:00+08:00",
            "--expected-symbol",
            "00700.HK",
            "--coverage-complete",
            "--quality-only",
        ],
    )

    main()

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    quality = (output_dir / "data_quality_report.csv").read_text(encoding="utf-8")
    assert manifest["capture_window_complete"] is False
    assert manifest["coverage_complete"] is False
    assert manifest["data_quality_rows"] == 1
    assert "active_seat_disclosure_coverage" in quality
    assert "00700.HK" in quality
    assert not (output_dir / "feature_snapshots.csv").exists()


def test_quality_only_reports_a_completely_absent_expected_symbol(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text("", encoding="utf-8")
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart-money",
            "--events-jsonl", str(events_path),
            "--output-dir", str(output_dir),
            "--dataset-mode", "historical_replay",
            "--direction-convention", DirectionConvention.VENDOR_DOC.value,
            "--expected-open", "2026-01-05T09:30:00+08:00",
            "--expected-end", "2026-01-05T16:00:00+08:00",
            "--expected-symbol", "00939.HK",
            "--session-start", "2026-01-05T09:30:00+08:00",
            "--coverage-complete",
            "--quality-only",
        ],
    )

    main()

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    quality = (output_dir / "data_quality_report.csv").read_text(encoding="utf-8")
    assert manifest["events"] == 0
    assert manifest["data_quality_rows"] == 1
    assert manifest["coverage_complete"] is False
    assert "00939.HK" in quality


def test_factor_replay_requires_independent_side_verification(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "output"
    write_jsonl(
        events_path,
        [
            trade(1, 1_767_576_601_000, "1"),
            {
                "kind": "l2thousand",
                "symbol": "00700.HK",
                "captured_at": "2026-01-05T09:30:01+08:00",
                "payload": {
                    "time": 1_767_576_601_000,
                    "bidPrice": [399.8],
                    "bidVolume": [10_000],
                    "askPrice": [400.0],
                    "askVolume": [8_000],
                },
            },
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart-money",
            "--events-jsonl", str(events_path),
            "--output-dir", str(output_dir),
            "--dataset-mode", "historical_replay",
            "--direction-convention", DirectionConvention.VENDOR_DOC.value,
            "--expected-open", "2026-01-05T09:30:00+08:00",
            "--expected-end", "2026-01-05T16:00:00+08:00",
            "--expected-symbol", "00700.HK",
            "--session-start", "2026-01-05T09:30:01+08:00",
        ],
    )

    with pytest.raises(ValueError, match="side verification"):
        main()

    assert (output_dir / "data_quality_report.csv").exists()
    assert not (output_dir / "feature_snapshots.csv").exists()


def test_factor_replay_rejects_incomplete_coverage_even_with_side_verification(
    tmp_path, monkeypatch
) -> None:
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "output"
    verification_path = tmp_path / "side-verification.json"
    write_jsonl(
        events_path,
        [
            trade(1, 1_767_576_601_000, "1"),
            {
                "kind": "l2thousand",
                "symbol": "00700.HK",
                "captured_at": "2026-01-05T09:30:01+08:00",
                "payload": {
                    "time": 1_767_576_601_000,
                    "bidPrice": [399.8],
                    "bidVolume": [10_000],
                    "askPrice": [400.0],
                    "askVolume": [8_000],
                },
            },
        ],
    )
    verification_path.write_text(
        json.dumps(
            {
                "verified": True,
                "verified_at": "2026-01-05T16:10:00+08:00",
                "direction_convention": DirectionConvention.VENDOR_DOC.value,
                "evidence": "Independent exchange reconciliation",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart-money",
            "--events-jsonl", str(events_path),
            "--output-dir", str(output_dir),
            "--dataset-mode", "historical_replay",
            "--direction-convention", DirectionConvention.VENDOR_DOC.value,
            "--expected-open", "2026-01-05T09:30:00+08:00",
            "--expected-end", "2026-01-05T16:00:00+08:00",
            "--expected-symbol", "00700.HK",
            "--session-start", "2026-01-05T09:30:00+08:00",
            "--side-verification-file", str(verification_path),
            "--coverage-complete",
        ],
    )

    with pytest.raises(ValueError, match="coverage"):
        main()

    assert (output_dir / "data_quality_report.csv").exists()
    assert not (output_dir / "feature_snapshots.csv").exists()


def test_historical_archive_backtest_uses_event_time_without_live_capture_evidence(
    tmp_path, monkeypatch
) -> None:
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "output"
    verification_path = tmp_path / "side-verification.json"
    archive_summary_path = tmp_path / "octopus-export-summary.json"
    archive_lineage_path = tmp_path / "vault-beast-manifest.json"
    first_timestamp_ms = 1_767_576_601_000
    second_timestamp_ms = first_timestamp_ms + 1_000
    delayed_capture = "2026-01-05T16:00:00+08:00"
    write_jsonl(
        events_path,
        [
            trade(1, first_timestamp_ms, "1")
            | {"captured_at": delayed_capture, "captured_at_source": "vault_file_mtime_ns"},
            {
                "kind": "l2thousand",
                "symbol": "00700.HK",
                "captured_at": delayed_capture,
                "captured_at_source": "vault_file_mtime_ns",
                "payload": {
                    "time": first_timestamp_ms,
                    "bidPrice": [399.8],
                    "bidVolume": [10_000],
                    "askPrice": [400.0],
                    "askVolume": [8_000],
                },
            },
            trade(2, second_timestamp_ms, "2")
            | {"captured_at": delayed_capture, "captured_at_source": "vault_file_mtime_ns"},
            {
                "kind": "l2thousand",
                "symbol": "00700.HK",
                "captured_at": delayed_capture,
                "captured_at_source": "vault_file_mtime_ns",
                "payload": {
                    "time": second_timestamp_ms,
                    "bidPrice": [399.9],
                    "bidVolume": [10_000],
                    "askPrice": [400.1],
                    "askVolume": [8_000],
                },
            },
        ],
    )
    verification_path.write_text(
        json.dumps(
            {
                "verified": True,
                "verified_at": "2026-01-05T16:10:00+08:00",
                "direction_convention": DirectionConvention.VENDOR_DOC.value,
                "evidence": "XTQuant vendor direction specification",
            }
        ),
        encoding="utf-8",
    )
    archive_summary_path.write_text(
        json.dumps(
            {
                "dataset_mode": "vault_octopus_live_export",
                "trade_date": "2026-01-05",
                "expected_symbols": ["00700.HK"],
                "vault_export_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
                "source_snapshot_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    write_archive_lineage(archive_lineage_path, events_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart-money",
            "--events-jsonl", str(events_path),
            "--output-dir", str(output_dir),
            "--dataset-mode", "historical_archive_backtest",
            "--direction-convention", DirectionConvention.VENDOR_DOC.value,
            "--expected-open", "2026-01-05T09:30:00+08:00",
            "--expected-end", "2026-01-05T16:00:00+08:00",
            "--expected-symbol", "00700.HK",
            "--session-start", "2026-01-05T09:30:00+08:00",
            "--side-verification-file", str(verification_path),
            "--historical-source-summary", str(archive_summary_path),
            "--vault-beast-manifest", str(archive_lineage_path),
        ],
    )

    main()

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["historical_backtest_allowed"] is True
    assert manifest["realtime_capture_evidence_required"] is False
    assert manifest["live_claims_allowed"] is False
    assert manifest["executable_claims_allowed"] is False
    assert manifest["replay_clock"] == "event_time_assumed"
    assert manifest["historical_source_summary"]["source_snapshot_sha256"] == "a" * 64
    assert manifest["historical_source_summary"]["vault_export_sha256"] == hashlib.sha256(
        events_path.read_bytes()
    ).hexdigest()
    assert manifest["vault_beast_lineage"]["vault"]["content_sha256"] == "a" * 64
    assert manifest["features"] == 2


def test_historical_archive_quality_only_requires_hash_bound_lineage(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    output_dir = tmp_path / "output"
    archive_summary_path = tmp_path / "octopus-export-summary.json"
    write_jsonl(events_path, [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart-money",
            "--events-jsonl", str(events_path),
            "--output-dir", str(output_dir),
            "--dataset-mode", "historical_archive_backtest",
            "--direction-convention", DirectionConvention.VENDOR_DOC.value,
            "--expected-open", "2026-01-05T09:30:00+08:00",
            "--expected-end", "2026-01-05T16:00:00+08:00",
            "--expected-symbol", "00700.HK",
            "--session-start", "2026-01-05T09:30:00+08:00",
            "--quality-only",
        ],
    )

    with pytest.raises(ValueError, match="historical-source-summary"):
        main()

    assert not (output_dir / "manifest.json").exists()
    archive_summary_path.write_text(
        json.dumps(
            {
                "dataset_mode": "vault_octopus_live_export",
                "trade_date": "2026-01-05",
                "expected_symbols": ["00700.HK"],
                "vault_export_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
                "source_snapshot_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        sys.argv + ["--historical-source-summary", str(archive_summary_path)],
    )

    with pytest.raises(ValueError, match="vault-beast-manifest"):
        main()


def test_side_verification_artifact_must_match_the_selected_contract(tmp_path) -> None:
    path = tmp_path / "side-verification.json"
    path.write_text(
        json.dumps(
            {
                "verified": True,
                "verified_at": "2026-01-05T16:10:00+08:00",
                "direction_convention": DirectionConvention.VENDOR_DOC.value,
                "evidence": "Independent exchange-tape reconciliation report QA-2026-01-05",
            }
        ),
        encoding="utf-8",
    )

    verification = load_side_verification(path, DirectionConvention.VENDOR_DOC)

    assert verification["verified"] is True
    with pytest.raises(ValueError, match="does not match"):
        load_side_verification(path, DirectionConvention.THOUSAND_LEGACY)


def test_trade_capture_evidence_requires_full_heartbeat_envelope(tmp_path) -> None:
    path = tmp_path / "capture-evidence.json"
    path.write_text(
        json.dumps(
            {
                "source": "xtquant.hktransaction",
                "trade_date": "2026-01-05",
                "events_sha256": "a" * 64,
                "symbols": {
                    "00700.HK": {
                        "subscription_acknowledged": True,
                        "subscribed_at": "2026-01-05T09:29:59+08:00",
                        "heartbeats": [
                            "2026-01-05T09:30:00+08:00",
                            "2026-01-05T09:31:01+08:00",
                            "2026-01-05T16:00:00+08:00",
                        ],
                        "dropped_callback_count": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    audit = load_trade_capture_evidence(
        path,
        expected_open=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
        expected_end=datetime.fromisoformat("2026-01-05T16:00:00+08:00"),
        expected_symbols=("00700.HK",),
        events_sha256="a" * 64,
    )

    symbol_audit = audit.for_symbol("00700.HK")
    assert symbol_audit is not None
    assert symbol_audit.max_heartbeat_gap_seconds > 60.0
    assert not symbol_audit.capture_complete


def test_trade_capture_evidence_must_link_to_manifest_source_export(tmp_path) -> None:
    path = tmp_path / "capture-evidence.json"
    path.write_text(
        json.dumps(
            {
                "source": "xtquant.hktransaction",
                "trade_date": "2026-01-05",
                "events_sha256": "a" * 64,
                "source_events_sha256": "b" * 64,
                "symbols": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source export"):
        load_trade_capture_evidence(
            path,
            expected_open=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            expected_end=datetime.fromisoformat("2026-01-05T16:00:00+08:00"),
            expected_symbols=(),
            events_sha256="a" * 64,
            source_events_sha256="c" * 64,
        )


def test_trade_capture_evidence_accepts_full_active_session_heartbeats(tmp_path) -> None:
    path = tmp_path / "capture-evidence.json"
    open_time = datetime.fromisoformat("2026-01-05T09:30:00+08:00")
    end_time = open_time.replace(hour=16, minute=0)
    offsets = (*range(0, 9_001, 60), *range(12_600, 23_401, 60))
    heartbeats = [(open_time + timedelta(seconds=offset)).isoformat() for offset in offsets]
    path.write_text(
        json.dumps(
            {
                "source": "xtquant.hktransaction",
                "trade_date": "2026-01-05",
                "events_sha256": "b" * 64,
                "symbols": {
                    "00700.HK": {
                        "subscription_acknowledged": True,
                        "subscribed_at": "2026-01-05T09:29:59+08:00",
                        "heartbeats": heartbeats,
                        "dropped_callback_count": 0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    audit = load_trade_capture_evidence(
        path,
        expected_open=open_time,
        expected_end=end_time,
        expected_symbols=("00700.HK",),
        events_sha256="b" * 64,
    )

    symbol_audit = audit.for_symbol("00700.HK")
    assert symbol_audit is not None
    assert symbol_audit.max_heartbeat_gap_seconds == pytest.approx(60.0)
    assert symbol_audit.capture_complete


def test_snapshot_interval_must_be_strictly_positive() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="positive"):
        _positive_milliseconds("0")


def test_output_directory_must_not_mix_with_a_previous_run(tmp_path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "feature_snapshots.csv").write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="non-empty"):
        _prepare_output_dir(output_dir)


def test_dropped_callback_count_must_be_a_nonnegative_json_integer(tmp_path) -> None:
    path = tmp_path / "capture-evidence.json"
    path.write_text(
        json.dumps(
            {
                "source": "xtquant.hktransaction",
                "trade_date": "2026-01-05",
                "events_sha256": "c" * 64,
                "symbols": {
                    "00700.HK": {
                        "subscription_acknowledged": True,
                        "subscribed_at": "2026-01-05T09:29:59+08:00",
                        "heartbeats": [
                            "2026-01-05T09:30:00+08:00",
                            "2026-01-05T16:00:00+08:00",
                        ],
                        "dropped_callback_count": 0.5,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="nonnegative JSON integer"):
        load_trade_capture_evidence(
            path,
            expected_open=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            expected_end=datetime.fromisoformat("2026-01-05T16:00:00+08:00"),
            expected_symbols=("00700.HK",),
            events_sha256="c" * 64,
        )

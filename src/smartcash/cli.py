from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import BookSnapshotEvent, SessionContext
from .data_quality import (
    BookInputAudit,
    BookInputAuditor,
    SymbolTradeCaptureAudit,
    TapeAudit,
    TapeAuditor,
    TradeCaptureAudit,
    active_hk_seconds_between,
    build_data_quality_rows,
)
from .engine import SmartCashEngine
from .identity import ExternalIdentityAlias, IdentityRecord, IdentityRegistry
from .integrations.vault_beast import load_vault_beast_manifest
from .replay import MarkoutLabeler, MarketEvent, ReplayRunner
from .reporting import feature_row, label_row, shock_rows, summary_rows, write_csv
from .xtquant import DirectionConvention, normalize_hktransaction, normalize_l2thousand


def _date(value: str, default: date | None = None) -> date | None:
    return datetime.fromisoformat(value).date() if value else default


def _registry(path: Path | None) -> IdentityRegistry:
    if path is None:
        return IdentityRegistry()
    records = []
    identity_file_sha256 = _sha256_file(path)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            external_aliases = ()
            ccass_participant_id = str(
                row.get("ccass_participant_id") or row.get("participant_id") or ""
            ).strip()
            if ccass_participant_id:
                external_aliases = (
                    ExternalIdentityAlias(
                        source=str(row.get("external_alias_source") or "ccass_reference"),
                        alias_type="participant_id",
                        value=ccass_participant_id,
                    ),
                )
            records.append(
                IdentityRecord(
                    seat_code=str(row["seat_code"]).zfill(4),
                    seat_full_name=row.get("seat_full_name") or str(row["seat_code"]),
                    seat_display_name=row.get("seat_display_name") or str(row["seat_code"]),
                    broker_entity_id=row["broker_entity_id"],
                    broker_entity_full_name=row["broker_entity_full_name"],
                    broker_entity_display_name=(
                        row.get("broker_entity_display_name")
                        or row["broker_entity_full_name"]
                    ),
                    external_aliases=external_aliases,
                    skill_score=float(row.get("skill_score", 0.0)),
                    effective_from=_date(row["effective_from"]) or date.min,
                    effective_to=_date(row.get("effective_to", "")),
                    mapping_source=str(row.get("mapping_source") or "identity_csv"),
                    mapping_version=str(row.get("mapping_version") or identity_file_sha256),
                )
            )
    return IdentityRegistry(tuple(records))


def load_events(
    path: Path,
    convention: DirectionConvention,
    *,
    max_arrival_latency_ms: float = 1_000.0,
    observed_captured_at_sources: set[str] | None = None,
) -> tuple[list[MarketEvent], TapeAudit, BookInputAudit]:
    events = []
    tape_auditor = TapeAuditor(max_arrival_latency_ms=max_arrival_latency_ms)
    book_auditor = BookInputAuditor(max_arrival_latency_ms=max_arrival_latency_ms)
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row: dict[str, Any] = json.loads(line)
            if observed_captured_at_sources is not None:
                raw_captured_at_source = row.get("captured_at_source")
                observed_captured_at_sources.add(
                    raw_captured_at_source.strip()
                    if isinstance(raw_captured_at_source, str)
                    else ""
                )
            kind = str(row.get("kind", ""))
            symbol = str(row.get("symbol", ""))
            payload = row.get("payload", row)
            captured_at_value = row.get("captured_at")
            captured_at = datetime.fromisoformat(str(captured_at_value)) if captured_at_value else None
            if captured_at is not None and captured_at.tzinfo is None:
                raise ValueError(f"line {line_number}: captured_at must be timezone-aware")
            if kind == "hktransaction":
                event = normalize_hktransaction(
                    symbol=symbol,
                    raw=payload,
                    convention=convention,
                    captured_at=captured_at,
                )
                tape_auditor.record(
                    event,
                    raw_sequence=payload.get("seq", payload.get("Seq")),
                    captured_at=captured_at,
                )
                events.append(event)
            elif kind == "l2thousand":
                try:
                    event = normalize_l2thousand(
                        symbol=symbol,
                        raw=payload,
                        captured_at=captured_at,
                    )
                except ValueError as error:
                    book_auditor.record_rejection(symbol, error)
                    continue
                book_auditor.record_valid(event, captured_at=captured_at)
                events.append(event)
            elif kind in {"broker_queue", "hkbrokerqueueex"}:
                raise ValueError(f"line {line_number}: broker_queue cannot enter the trade/book replay")
            else:
                raise ValueError(f"line {line_number}: unsupported event kind {kind!r}")
    return events, tape_auditor.snapshot(), book_auditor.snapshot()


def load_side_verification(path: Path, convention: DirectionConvention) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    verified_at = datetime.fromisoformat(str(payload.get("verified_at") or ""))
    if verified_at.tzinfo is None:
        raise ValueError("side verification timestamp must be timezone-aware")
    if payload.get("verified") is not True:
        raise ValueError("side verification artifact is not approved")
    if payload.get("direction_convention") != convention.value:
        raise ValueError("side verification convention does not match replay convention")
    if not str(payload.get("evidence") or "").strip():
        raise ValueError("side verification evidence is required")
    return payload


def load_trade_capture_evidence(
    path: Path,
    *,
    expected_open: datetime,
    expected_end: datetime,
    expected_symbols: tuple[str, ...],
    events_sha256: str,
    source_events_sha256: str | None = None,
) -> TradeCaptureAudit:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("trade_date") != expected_open.date().isoformat():
        raise ValueError("trade capture evidence date does not match expected_open")
    if payload.get("events_sha256") != events_sha256:
        raise ValueError("trade capture evidence is not bound to this events file")
    if (
        source_events_sha256 is not None
        and payload.get("source_events_sha256") != source_events_sha256
    ):
        raise ValueError("trade capture evidence is not bound to the manifest source export")
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, dict):
        raise ValueError("trade capture evidence symbols must be an object")
    expected_symbol_set = set(expected_symbols)
    unexpected_symbols = set(map(str, raw_symbols)) - expected_symbol_set
    if unexpected_symbols:
        raise ValueError(f"unexpected trade capture evidence symbols: {sorted(unexpected_symbols)}")
    audits = []
    for symbol in sorted(expected_symbol_set):
        raw = raw_symbols.get(symbol)
        if not isinstance(raw, dict):
            continue
        subscribed_at = _capture_timestamp(raw.get("subscribed_at"), symbol=symbol)
        heartbeat_values = raw.get("heartbeats")
        if not isinstance(heartbeat_values, list):
            raise ValueError(f"trade capture heartbeats must be a list for {symbol}")
        heartbeats = tuple(
            _capture_timestamp(value, symbol=symbol, required=True) for value in heartbeat_values
        )
        heartbeat_ordered = all(
            current > previous
            for previous, current in zip(heartbeats, heartbeats[1:], strict=False)
        )
        heartbeat_gaps = [
            active_hk_seconds_between(previous, current)
            for previous, current in zip(heartbeats, heartbeats[1:], strict=False)
        ]
        if heartbeats:
            heartbeat_gaps.extend(
                (
                    max(0.0, (heartbeats[0] - expected_open).total_seconds()),
                    active_hk_seconds_between(heartbeats[-1], expected_end),
                )
            )
        audits.append(
            SymbolTradeCaptureAudit(
                symbol=symbol,
                source=str(payload.get("source") or ""),
                subscription_acknowledged=raw.get("subscription_acknowledged") is True,
                subscribed_at=subscribed_at,
                first_heartbeat_at=heartbeats[0] if heartbeats else None,
                last_heartbeat_at=heartbeats[-1] if heartbeats else None,
                heartbeat_count=len(heartbeats),
                max_heartbeat_gap_seconds=max(heartbeat_gaps, default=float("inf")),
                dropped_callback_count=_nonnegative_json_integer(
                    raw.get("dropped_callback_count"),
                    field="dropped_callback_count",
                    symbol=symbol,
                ),
                expected_open=expected_open,
                expected_end=expected_end,
                heartbeat_ordered=heartbeat_ordered,
            )
        )
    return TradeCaptureAudit(tuple(audits))


def _capture_timestamp(
    value: object,
    *,
    symbol: str,
    required: bool = False,
) -> datetime | None:
    if value in (None, ""):
        if required:
            raise ValueError(f"trade capture timestamp is required for {symbol}")
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=8):
        raise ValueError(f"trade capture timestamp must use Asia/Hong_Kong (+08:00) for {symbol}")
    return parsed


def _positive_milliseconds(value: str) -> int:
    milliseconds = int(value)
    if milliseconds <= 0:
        raise argparse.ArgumentTypeError("snapshot milliseconds must be positive")
    return milliseconds


def _nonnegative_json_integer(value: object, *, field: str, symbol: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative JSON integer for {symbol}")
    return value


def _prepare_output_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise ValueError(f"output path is not a directory: {path}")
        if any(path.iterdir()):
            raise ValueError(f"output directory is non-empty; use a new run directory: {path}")
    else:
        path.mkdir(parents=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _historical_archive_events(events: list[MarketEvent]) -> list[MarketEvent]:
    """Replay an archive on its exchange-event clock, never as live arrival evidence."""

    return sorted(
        (replace(event, captured_at=event.event_ts) for event in events),
        key=_historical_archive_event_sort_key,
    )


def _historical_archive_event_sort_key(event: MarketEvent) -> tuple[object, ...]:
    """Use a documented deterministic ordering for equal exchange timestamps."""

    if isinstance(event, BookSnapshotEvent):
        return (
            event.event_ts,
            0,
            event.symbol,
            event.source,
            tuple((level.price, level.size, level.order_count) for level in event.bids),
            tuple((level.price, level.size, level.order_count) for level in event.asks),
        )
    return (event.event_ts, 1, event.symbol, event.source, event.trade_id)


def load_historical_source_summary(
    path: Path,
    *,
    events_sha256: str,
    expected_open: datetime,
    expected_symbols: tuple[str, ...],
) -> dict[str, object]:
    """Bind an event-time archive replay to its immutable Vault export summary."""

    content = path.read_bytes()
    try:
        summary = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("historical source summary must be UTF-8 JSON") from error
    if not isinstance(summary, dict):
        raise ValueError("historical source summary must be an object")
    if summary.get("dataset_mode") != "vault_octopus_live_export":
        raise ValueError("historical source summary must describe a Vault Octopus-Live export")
    if summary.get("trade_date") != expected_open.date().isoformat():
        raise ValueError("historical source summary trade date does not match expected_open")
    if summary.get("vault_export_sha256") != events_sha256:
        raise ValueError("historical source summary is not bound to this events file")
    if set(map(str, summary.get("expected_symbols") or ())) != set(expected_symbols):
        raise ValueError("historical source summary symbols do not match the replay universe")
    source_snapshot_sha256 = str(summary.get("source_snapshot_sha256") or "")
    if len(source_snapshot_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in source_snapshot_sha256.lower()
    ):
        raise ValueError("historical source summary requires source_snapshot_sha256")
    return {
        "summary_sha256": hashlib.sha256(content).hexdigest(),
        "source_snapshot_sha256": source_snapshot_sha256.lower(),
        "vault_export_sha256": events_sha256,
        "trade_date": str(summary["trade_date"]),
        "expected_symbols": sorted(map(str, summary["expected_symbols"])),
    }


def _validate_historical_archive_lineage(
    *,
    historical_source_summary: dict[str, object] | None,
    vault_beast_manifest: Any | None,
) -> None:
    """Require canonical Vault/Beast provenance even for quality-only archive inspection."""

    if historical_source_summary is None:
        raise ValueError("historical archive backtest requires --historical-source-summary")
    if vault_beast_manifest is None:
        raise ValueError("historical archive backtest requires --vault-beast-manifest")
    if historical_source_summary["vault_export_sha256"] != vault_beast_manifest.vault.export_sha256:
        raise ValueError("historical source summary export hash does not match Vault/Beast lineage")
    if (
        historical_source_summary["source_snapshot_sha256"]
        != vault_beast_manifest.vault.content_sha256
    ):
        raise ValueError("historical source summary snapshot hash does not match Vault/Beast lineage")


def _archive_disclaimers(historical_archive_backtest: bool) -> dict[str, object]:
    if not historical_archive_backtest:
        return {}
    return {
        "live_claims_allowed": False,
        "executable_claims_allowed": False,
        "event_time_tie_break": "book_then_trade; symbol; source; payload_or_trade_id",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay XTQuant HK trades and L2 snapshots into causal SmartCash features"
    )
    parser.add_argument("--events-jsonl", type=Path, required=True)
    parser.add_argument("--identity-csv", type=Path)
    parser.add_argument("--vault-beast-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--direction-convention", choices=[item.value for item in DirectionConvention], required=True)
    parser.add_argument("--session-start", required=True)
    parser.add_argument("--expected-open", required=True)
    parser.add_argument("--expected-end", required=True)
    parser.add_argument(
        "--expected-symbol",
        action="append",
        required=True,
        help="Expected symbol; repeat once per member of the acceptance universe",
    )
    parser.add_argument(
        "--dataset-mode",
        choices=("historical_replay", "historical_archive_backtest", "live_session_capture"),
        required=True,
    )
    parser.add_argument(
        "--coverage-complete",
        action="store_true",
        help="Claim a full requested session; the CLI still validates duration, endpoints, tape and L2 gaps",
    )
    parser.add_argument("--max-book-gap-seconds", type=float, default=5.0)
    parser.add_argument("--max-arrival-latency-ms", type=float, default=1_000.0)
    parser.add_argument("--trade-capture-evidence-file", type=Path)
    parser.add_argument("--historical-source-summary", type=Path)
    parser.add_argument("--side-verification-file", type=Path)
    parser.add_argument(
        "--quality-only",
        action="store_true",
        help="Write only Phase 0 data-quality outputs; no signed-flow features or labels",
    )
    parser.add_argument("--snapshot-milliseconds", type=_positive_milliseconds, default=1_000)
    args = parser.parse_args()
    _prepare_output_dir(args.output_dir)

    direction_convention = DirectionConvention(args.direction_convention)
    events_sha256 = _sha256_file(args.events_jsonl)
    vault_beast_manifest = (
        load_vault_beast_manifest(
            args.vault_beast_manifest,
            expected_artifact_sha256=events_sha256,
        )
        if args.vault_beast_manifest is not None
        else None
    )
    observed_captured_at_sources: set[str] = set()
    events, tape_audit, book_input_audit = load_events(
        args.events_jsonl,
        direction_convention,
        max_arrival_latency_ms=args.max_arrival_latency_ms,
        observed_captured_at_sources=observed_captured_at_sources,
    )
    if vault_beast_manifest is not None:
        vault_beast_manifest.validate_captured_at_sources(observed_captured_at_sources)
    if _sha256_file(args.events_jsonl) != events_sha256:
        raise ValueError("events file changed while it was being audited")
    session_start = datetime.fromisoformat(args.session_start)
    expected_open = datetime.fromisoformat(args.expected_open)
    expected_end = datetime.fromisoformat(args.expected_end)
    trade_capture_audit = (
        load_trade_capture_evidence(
            args.trade_capture_evidence_file,
            expected_open=expected_open,
            expected_end=expected_end,
            expected_symbols=tuple(args.expected_symbol),
            events_sha256=events_sha256,
            source_events_sha256=(
                vault_beast_manifest.vault.export_sha256
                if vault_beast_manifest is not None
                else None
            ),
        )
        if args.trade_capture_evidence_file is not None
        else TradeCaptureAudit(())
    )
    trade_dates = {event.event_ts.date() for event in events}
    if len(trade_dates) > 1:
        raise ValueError("one replay invocation must contain at most one trade date")
    if trade_dates and trade_dates != {expected_open.date()}:
        raise ValueError("event trade date does not match expected_open")
    trade_date = expected_open.date()
    registry = _registry(args.identity_csv)
    quality_rows = build_data_quality_rows(
        events,
        tape_audit=tape_audit,
        trade_capture_audit=trade_capture_audit,
        book_input_audit=book_input_audit,
        expected_open=expected_open,
        expected_end=expected_end,
        expected_symbols=tuple(args.expected_symbol),
        max_book_gap_seconds=args.max_book_gap_seconds,
        identity_registry=registry,
    )
    max_book_gap = max((row.max_book_gap_seconds for row in quality_rows), default=float("inf"))
    capture_window_complete = bool(
        quality_rows
        and all(
            row.tape_complete
            and row.trade_capture_complete
            and row.book_input_complete
            and row.book_coverage_complete
            for row in quality_rows
        )
    )
    coverage_complete = bool(
        args.coverage_complete
        and quality_rows
        and all(row.combined_complete for row in quality_rows)
    )
    historical_archive_backtest = args.dataset_mode == "historical_archive_backtest"
    replayed = args.dataset_mode in {"historical_replay", "historical_archive_backtest"}
    historical_source_summary = (
        load_historical_source_summary(
            args.historical_source_summary,
            events_sha256=events_sha256,
            expected_open=expected_open,
            expected_symbols=tuple(args.expected_symbol),
        )
        if historical_archive_backtest and args.historical_source_summary is not None
        else None
    )
    if historical_archive_backtest:
        _validate_historical_archive_lineage(
            historical_source_summary=historical_source_summary,
            vault_beast_manifest=vault_beast_manifest,
        )
    write_csv(args.output_dir / "data_quality_report.csv", [row.to_row() for row in quality_rows])
    side_verification = (
        load_side_verification(args.side_verification_file, direction_convention)
        if args.side_verification_file is not None
        else None
    )
    if args.quality_only:
        manifest = {
            "dataset_mode": args.dataset_mode,
            "quality_only": True,
            "events": len(events),
            "features": 0,
            "labels": 0,
            "direction_convention": args.direction_convention,
            "side_verified": side_verification is not None,
            "sessionStart": args.session_start,
            "expectedEnd": args.expected_end,
            "replayed": replayed,
            "coverage_claimed": args.coverage_complete,
            "capture_window_complete": capture_window_complete,
            "coverage_complete": coverage_complete,
            "historical_backtest_allowed": historical_archive_backtest,
            "realtime_capture_evidence_required": not historical_archive_backtest,
            "replay_clock": "event_time_assumed" if historical_archive_backtest else "captured_at",
            **_archive_disclaimers(historical_archive_backtest),
            "historical_source_summary": historical_source_summary,
            "expected_symbols": args.expected_symbol,
            "trade_capture_evidence_file": (
                str(args.trade_capture_evidence_file)
                if args.trade_capture_evidence_file is not None
                else None
            ),
            "trade_capture_complete": all(
                row.trade_capture_complete for row in quality_rows
            ),
            "required_active_session_seconds": quality_rows[0].active_session_seconds,
            "max_book_gap_seconds": max_book_gap,
            "max_arrival_latency_ms": args.max_arrival_latency_ms,
            "tape_complete": tape_audit.tape_complete,
            "trade_count": tape_audit.trade_count,
            "sequence_present": tape_audit.sequence_present,
            "out_of_order_count": tape_audit.out_of_order_count,
            "duplicate_trade_id_count": tape_audit.duplicate_trade_id_count,
            "sequence_gap_count": tape_audit.sequence_gap_count,
            "data_quality_rows": len(quality_rows),
            "vault_beast_lineage": (
                vault_beast_manifest.to_dict() if vault_beast_manifest is not None else None
            ),
        }
        with (args.output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        print(json.dumps(manifest, ensure_ascii=False))
        return
    if side_verification is None:
        raise ValueError("factor replay requires an independent side verification artifact")
    if not historical_archive_backtest and not coverage_complete:
        raise ValueError(
            "factor replay requires --coverage-complete and every expected symbol to pass coverage"
        )
    if args.dataset_mode == "historical_replay" and vault_beast_manifest is None:
        raise ValueError("historical factor replay requires a Vault/Beast lineage manifest")
    if historical_archive_backtest and not all(
        row.trade_count and row.book_count for row in quality_rows
    ):
        raise ValueError(
            "historical archive backtest requires at least one valid trade and L2 book per expected symbol"
        )
    replay_events = _historical_archive_events(events) if historical_archive_backtest else events
    engine = SmartCashEngine(identity_registry=registry)
    engine.set_session(
        SessionContext(
            trade_date,
            expected_open,
            session_start,
            replayed,
            coverage_complete,
        )
    )
    first = replay_events[0].event_ts
    last = replay_events[-1].event_ts
    step = timedelta(milliseconds=args.snapshot_milliseconds)
    snapshot_times = []
    current = first
    while current <= last:
        snapshot_times.append(current)
        current += step
    features = ReplayRunner(engine).run(replay_events, snapshot_times=tuple(snapshot_times))
    books = [event for event in replay_events if isinstance(event, BookSnapshotEvent)]
    labels = [label for feature in features for label in MarkoutLabeler().label(feature, books)]
    dataset_mode = args.dataset_mode
    shock_events, shock_outcomes = shock_rows(replay_events, dataset_mode=dataset_mode, features=features)
    write_csv(
        args.output_dir / "feature_snapshots.csv",
        [feature_row(feature, dataset_mode=dataset_mode) for feature in features],
    )
    write_csv(
        args.output_dir / "markout_labels.csv",
        [label_row(label, dataset_mode=dataset_mode) for label in labels],
    )
    write_csv(
        args.output_dir / "backtest_summary.csv",
        summary_rows(features, labels, dataset_mode=dataset_mode),
    )
    write_csv(args.output_dir / "shock_events.csv", shock_events)
    write_csv(args.output_dir / "shock_outcomes.csv", shock_outcomes)
    manifest = {
        "dataset_mode": dataset_mode,
        "quality_only": False,
        "events": len(events),
        "features": len(features),
        "labels": len(labels),
        "direction_convention": args.direction_convention,
        "side_verified": True,
        "side_verification_file": str(args.side_verification_file),
        "sessionStart": args.session_start,
        "expectedEnd": args.expected_end,
        "replayed": replayed,
        "coverage_claimed": args.coverage_complete,
        "capture_window_complete": capture_window_complete,
        "coverage_complete": coverage_complete,
        "historical_backtest_allowed": historical_archive_backtest,
        "realtime_capture_evidence_required": not historical_archive_backtest,
        "replay_clock": "event_time_assumed" if historical_archive_backtest else "captured_at",
        "historical_source_summary": historical_source_summary,
        "expected_symbols": args.expected_symbol,
        "trade_capture_evidence_file": (
            str(args.trade_capture_evidence_file)
            if args.trade_capture_evidence_file is not None
            else None
        ),
        "trade_capture_complete": all(row.trade_capture_complete for row in quality_rows),
        "required_active_session_seconds": quality_rows[0].active_session_seconds,
        "max_book_gap_seconds": max_book_gap,
        "max_arrival_latency_ms": args.max_arrival_latency_ms,
        "tape_complete": tape_audit.tape_complete,
        "trade_count": tape_audit.trade_count,
        "sequence_present": tape_audit.sequence_present,
        "out_of_order_count": tape_audit.out_of_order_count,
        "duplicate_trade_id_count": tape_audit.duplicate_trade_id_count,
        "sequence_gap_count": tape_audit.sequence_gap_count,
        "shock_events": len(shock_events),
        "shock_outcomes": len(shock_outcomes),
        "data_quality_rows": len(quality_rows),
        "vault_beast_lineage": (
            vault_beast_manifest.to_dict() if vault_beast_manifest is not None else None
        ),
        **_archive_disclaimers(historical_archive_backtest),
    }
    with (args.output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()

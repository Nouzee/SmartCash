from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import BookSnapshotEvent, SessionContext
from .engine import SmartMoneyEngine
from .identity import IdentityRecord, IdentityRegistry
from .replay import MarkoutLabeler, MarketEvent, ReplayRunner
from .reporting import feature_row, label_row, shock_rows, summary_rows, write_csv
from .xtquant import DirectionConvention, normalize_hktransaction, normalize_l2thousand


def _date(value: str, default: date | None = None) -> date | None:
    return datetime.fromisoformat(value).date() if value else default


def _registry(path: Path | None) -> IdentityRegistry:
    if path is None:
        return IdentityRegistry()
    records = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            records.append(
                IdentityRecord(
                    broker_code=str(row["broker_code"]).zfill(4),
                    broker_full_name=row["broker_full_name"],
                    broker_display_name=row.get("broker_display_name") or row["broker_full_name"],
                    participant_id=row.get("participant_id", ""),
                    participant_full_name=row.get("participant_full_name", ""),
                    participant_display_name=row.get("participant_display_name") or row.get("participant_full_name", ""),
                    skill_score=float(row.get("skill_score", 0.0)),
                    effective_from=_date(row["effective_from"]) or date.min,
                    effective_to=_date(row.get("effective_to", "")),
                )
            )
    return IdentityRegistry(tuple(records))


@dataclass(frozen=True, slots=True)
class TapeAudit:
    trade_count: int
    sequence_present: bool
    out_of_order_count: int
    duplicate_trade_id_count: int
    sequence_gap_count: int

    @property
    def tape_complete(self) -> bool:
        return bool(
            self.trade_count
            and self.sequence_present
            and not self.out_of_order_count
            and not self.duplicate_trade_id_count
            and not self.sequence_gap_count
        )


def load_events(
    path: Path,
    convention: DirectionConvention,
) -> tuple[list[MarketEvent], TapeAudit]:
    events = []
    last_trade_ts: dict[str, datetime] = {}
    seen_trade_ids: dict[str, set[str]] = {}
    last_sequence: dict[str, int] = {}
    out_of_order_count = 0
    duplicate_trade_id_count = 0
    sequence_gap_count = 0
    sequence_present = True
    trade_count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row: dict[str, Any] = json.loads(line)
            kind = str(row.get("kind", ""))
            symbol = str(row.get("symbol", ""))
            payload = row.get("payload", row)
            if kind == "hktransaction":
                event = normalize_hktransaction(symbol=symbol, raw=payload, convention=convention)
                previous_ts = last_trade_ts.get(symbol)
                if previous_ts is not None and event.event_ts < previous_ts:
                    out_of_order_count += 1
                last_trade_ts[symbol] = event.event_ts
                if event.trade_id:
                    identifiers = seen_trade_ids.setdefault(symbol, set())
                    if event.trade_id in identifiers:
                        duplicate_trade_id_count += 1
                    identifiers.add(event.trade_id)
                raw_sequence = payload.get("seq")
                try:
                    sequence = int(raw_sequence)
                except (TypeError, ValueError):
                    sequence_present = False
                else:
                    previous_sequence = last_sequence.get(symbol)
                    if previous_sequence is not None and sequence != previous_sequence + 1:
                        sequence_gap_count += 1
                    last_sequence[symbol] = sequence
                trade_count += 1
                events.append(event)
            elif kind == "l2thousand":
                events.append(normalize_l2thousand(symbol=symbol, raw=payload))
            elif kind in {"broker_queue", "hkbrokerqueueex"}:
                raise ValueError(f"line {line_number}: broker_queue cannot enter the trade/book replay")
            else:
                raise ValueError(f"line {line_number}: unsupported event kind {kind!r}")
    audit = TapeAudit(
        trade_count=trade_count,
        sequence_present=sequence_present,
        out_of_order_count=out_of_order_count,
        duplicate_trade_id_count=duplicate_trade_id_count,
        sequence_gap_count=sequence_gap_count,
    )
    return sorted(events, key=lambda event: event.event_ts), audit


def _book_coverage(
    events: list[MarketEvent],
    *,
    expected_open: datetime,
    max_gap_seconds: float,
) -> tuple[bool, float]:
    by_symbol: dict[str, list[datetime]] = {}
    for event in events:
        if isinstance(event, BookSnapshotEvent):
            by_symbol.setdefault(event.symbol, []).append(event.event_ts)
    if not by_symbol:
        return False, float("inf")
    largest_gap = 0.0
    for timestamps in by_symbol.values():
        first_delay = max(0.0, (timestamps[0] - expected_open).total_seconds())
        gaps = [
            (current - previous).total_seconds()
            for previous, current in zip(timestamps, timestamps[1:], strict=False)
        ]
        largest_gap = max(largest_gap, first_delay, *gaps)
    return largest_gap <= max_gap_seconds, largest_gap


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay XTQuant HK trades and L2 snapshots into causal smart-money features")
    parser.add_argument("--events-jsonl", type=Path, required=True)
    parser.add_argument("--identity-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--direction-convention", choices=[item.value for item in DirectionConvention], required=True)
    parser.add_argument("--session-start", required=True)
    parser.add_argument("--expected-open", required=True)
    parser.add_argument(
        "--dataset-mode",
        choices=("historical_replay", "live_session_capture"),
        required=True,
    )
    parser.add_argument(
        "--coverage-complete",
        action="store_true",
        help="Assert that the input starts at expected-open; the CLI still rejects excessive L2 gaps",
    )
    parser.add_argument("--max-book-gap-seconds", type=float, default=5.0)
    parser.add_argument("--snapshot-milliseconds", type=int, default=1_000)
    args = parser.parse_args()

    events, tape_audit = load_events(args.events_jsonl, DirectionConvention(args.direction_convention))
    if not events:
        raise ValueError("event input is empty")
    trade_dates = {event.event_ts.date() for event in events}
    if len(trade_dates) != 1:
        raise ValueError("one replay invocation must contain exactly one trade date")
    session_start = datetime.fromisoformat(args.session_start)
    expected_open = datetime.fromisoformat(args.expected_open)
    coverage_valid, max_book_gap = _book_coverage(
        events,
        expected_open=expected_open,
        max_gap_seconds=args.max_book_gap_seconds,
    )
    coverage_complete = bool(args.coverage_complete and coverage_valid and tape_audit.tape_complete)
    replayed = args.dataset_mode == "historical_replay"
    engine = SmartMoneyEngine(identity_registry=_registry(args.identity_csv))
    engine.set_session(
        SessionContext(
            next(iter(trade_dates)),
            expected_open,
            session_start,
            replayed,
            coverage_complete,
        )
    )
    first = events[0].event_ts
    last = events[-1].event_ts
    step = timedelta(milliseconds=args.snapshot_milliseconds)
    snapshot_times = []
    current = first
    while current <= last:
        snapshot_times.append(current)
        current += step
    features = ReplayRunner(engine).run(events, snapshot_times=tuple(snapshot_times))
    books = [event for event in events if isinstance(event, BookSnapshotEvent)]
    labels = [label for feature in features for label in MarkoutLabeler().label(feature, books)]
    dataset_mode = args.dataset_mode
    shock_events, shock_outcomes = shock_rows(events, dataset_mode=dataset_mode, features=features)
    args.output_dir.mkdir(parents=True, exist_ok=True)
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
        "events": len(events),
        "features": len(features),
        "labels": len(labels),
        "direction_convention": args.direction_convention,
        "sessionStart": args.session_start,
        "replayed": replayed,
        "coverage_claimed": args.coverage_complete,
        "coverage_complete": coverage_complete,
        "max_book_gap_seconds": max_book_gap,
        "tape_complete": tape_audit.tape_complete,
        "trade_count": tape_audit.trade_count,
        "sequence_present": tape_audit.sequence_present,
        "out_of_order_count": tape_audit.out_of_order_count,
        "duplicate_trade_id_count": tape_audit.duplicate_trade_id_count,
        "sequence_gap_count": tape_audit.sequence_gap_count,
        "shock_events": len(shock_events),
        "shock_outcomes": len(shock_outcomes),
    }
    with (args.output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()

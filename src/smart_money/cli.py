from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import BookSnapshotEvent, SessionContext
from .demo import _feature_row, _label_row, _summaries, _write_csv
from .engine import SmartMoneyEngine
from .identity import IdentityRecord, IdentityRegistry
from .replay import MarkoutLabeler, ReplayRunner
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


def _events(path: Path, convention: DirectionConvention):
    events = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row: dict[str, Any] = json.loads(line)
            kind = str(row.get("kind", ""))
            symbol = str(row.get("symbol", ""))
            payload = row.get("payload", row)
            if kind in {"hktransaction", "tick"}:
                events.append(normalize_hktransaction(symbol=symbol, raw=payload, convention=convention))
            elif kind in {"l2thousand", "l2_order_book"}:
                events.append(normalize_l2thousand(symbol=symbol, raw=payload))
            elif kind in {"broker_queue", "hkbrokerqueueex"}:
                raise ValueError(f"line {line_number}: broker_queue cannot enter the trade/book replay")
            else:
                raise ValueError(f"line {line_number}: unsupported event kind {kind!r}")
    return sorted(events, key=lambda event: event.event_ts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay XTQuant HK trades and L2 snapshots into causal smart-money features")
    parser.add_argument("--events-jsonl", type=Path, required=True)
    parser.add_argument("--identity-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--direction-convention", choices=[item.value for item in DirectionConvention], required=True)
    parser.add_argument("--session-start", required=True)
    parser.add_argument("--expected-open", required=True)
    parser.add_argument("--replayed", action="store_true")
    parser.add_argument("--snapshot-milliseconds", type=int, default=1_000)
    args = parser.parse_args()

    events = _events(args.events_jsonl, DirectionConvention(args.direction_convention))
    if not events:
        raise ValueError("event input is empty")
    trade_dates = {event.event_ts.date() for event in events}
    if len(trade_dates) != 1:
        raise ValueError("one replay invocation must contain exactly one trade date")
    session_start = datetime.fromisoformat(args.session_start)
    expected_open = datetime.fromisoformat(args.expected_open)
    engine = SmartMoneyEngine(identity_registry=_registry(args.identity_csv))
    engine.set_session(SessionContext(next(iter(trade_dates)), expected_open, session_start, args.replayed))
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
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "feature_snapshots.csv", [_feature_row(feature) for feature in features])
    _write_csv(args.output_dir / "markout_labels.csv", [_label_row(label) for label in labels])
    _write_csv(args.output_dir / "backtest_summary.csv", _summaries(features, labels))
    manifest = {
        "dataset_mode": "historical_replay" if args.replayed else "live_session_capture",
        "events": len(events),
        "features": len(features),
        "labels": len(labels),
        "direction_convention": args.direction_convention,
        "sessionStart": args.session_start,
        "replayed": args.replayed,
    }
    with (args.output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()

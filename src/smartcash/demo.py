from __future__ import annotations

import argparse
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from .contracts import AggressorSide, BookLevel, BookSnapshotEvent, SessionContext, TradeEvent
from .engine import SmartCashEngine
from .identity import IdentityRecord, IdentityRegistry
from .replay import MarkoutLabeler, ReplayRunner
from .reporting import feature_row, label_row, shock_rows, summary_rows, write_csv

BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def _identity_registry() -> IdentityRegistry:
    return IdentityRegistry(
        (
            IdentityRecord(
                "0101",
                "Seat 0101",
                "0101",
                "broker-alpha",
                "Alpha Institutional Securities Limited",
                "Alpha Inst",
                (),
                0.8,
                date(2020, 1, 1),
            ),
            IdentityRecord(
                "0102",
                "Seat 0102",
                "0102",
                "broker-broad-market",
                "Broad Market Securities Limited",
                "Broad Market",
                (),
                0.1,
                date(2020, 1, 1),
            ),
        )
    )


def _synthetic_events(duration_seconds: int, seed: int) -> list[BookSnapshotEvent | TradeEvent]:
    rng = random.Random(seed)
    events: list[BookSnapshotEvent | TradeEvent] = []
    for second in range(duration_seconds + 1):
        event_ts = BASE + timedelta(seconds=second)
        for symbol in ("00700.HK", "00939.HK"):
            if symbol == "00700.HK":
                mid = 100.0 + 0.002 * second + (0.35 if second >= 100 else 0.0)
                side = AggressorSide.BUY if rng.random() < 0.78 else AggressorSide.SELL
                bid_size, ask_size = 1_500, 500
                broker = "0101" if side is AggressorSide.BUY else "0102"
            else:
                mid = 50.0 + (0.0025 * second if second <= 140 else 0.35 - 0.0022 * (second - 140))
                side = AggressorSide.BUY if second <= 140 else AggressorSide.SELL
                if rng.random() < 0.25:
                    side = AggressorSide.SELL if side is AggressorSide.BUY else AggressorSide.BUY
                bid_size, ask_size = ((1_200, 500) if second <= 140 else (450, 1_300))
                broker = "0101" if side is AggressorSide.BUY else "0102"
            spread = 0.10 if second % 90 else 0.20
            book = BookSnapshotEvent(
                symbol=symbol,
                event_ts=event_ts,
                bids=(BookLevel(mid - spread / 2, bid_size), BookLevel(mid - spread / 2 - 0.05, bid_size // 2)),
                asks=(BookLevel(mid + spread / 2, ask_size), BookLevel(mid + spread / 2 + 0.05, ask_size // 2)),
                source="xtquant.l2thousand",
            )
            volume = rng.choice((500, 1_000, 2_000, 5_000))
            trade = TradeEvent(
                symbol=symbol,
                event_ts=event_ts,
                price=mid,
                volume=volume,
                turnover=mid * volume,
                aggressor_side=side,
                active_seat_code=broker,
                passive_seat_code="9999",
                trade_id=f"{symbol}-{second}",
                side_contract="synthetic_canonical",
                source="synthetic.hktransaction",
            )
            events.extend((book, trade))
    return events


def run_demo(output_dir: Path, *, duration_seconds: int = 720, seed: int = 7) -> dict[str, object]:
    if duration_seconds < 360:
        raise ValueError("duration_seconds must allow a five-minute markout")
    output_dir.mkdir(parents=True, exist_ok=True)
    events = _synthetic_events(duration_seconds, seed)
    engine = SmartCashEngine(identity_registry=_identity_registry())
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True, True))
    last_signal_second = duration_seconds - 300
    snapshot_times = tuple(BASE + timedelta(seconds=second) for second in range(60, last_signal_second + 1, 10))
    features = ReplayRunner(engine).run(events, snapshot_times=snapshot_times)
    books = [event for event in events if isinstance(event, BookSnapshotEvent)]
    labeler = MarkoutLabeler()
    labels = [label for feature in features for label in labeler.label(feature, books)]
    feature_rows = [feature_row(feature, dataset_mode="synthetic_demo") for feature in features]
    label_rows = [label_row(label, dataset_mode="synthetic_demo") for label in labels]
    summaries = summary_rows(features, labels, dataset_mode="synthetic_demo")
    shock_events, shock_outcomes = shock_rows(events, dataset_mode="synthetic_demo", features=features)
    write_csv(output_dir / "feature_snapshots.csv", feature_rows)
    write_csv(output_dir / "markout_labels.csv", label_rows)
    write_csv(output_dir / "backtest_summary.csv", summaries)
    write_csv(output_dir / "shock_events.csv", shock_events)
    write_csv(output_dir / "shock_outcomes.csv", shock_outcomes)
    manifest: dict[str, object] = {
        "dataset_mode": "synthetic_demo",
        "empirical_claims_allowed": False,
        "seed": seed,
        "duration_seconds": duration_seconds,
        "feature_rows": len(feature_rows),
        "label_rows": len(label_rows),
        "shock_events": len(shock_events),
        "shock_outcomes": len(shock_outcomes),
    }
    with (output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic synthetic SmartCash microstructure replay")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/demo"))
    parser.add_argument("--duration-seconds", type=int, default=720)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(run_demo(args.output_dir, duration_seconds=args.duration_seconds, seed=args.seed), ensure_ascii=False))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Iterable, Mapping

from .contracts import AggressorSide, BookLevel, BookSnapshotEvent, FeatureSnapshot, SessionContext, TradeEvent
from .engine import SmartMoneyEngine
from .identity import IdentityRecord, IdentityRegistry
from .replay import MarkoutLabel, MarkoutLabeler, ReplayRunner
from .shocks import MicrostructureObservation, ShockDetector, ShockLabeler

BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def _identity_registry() -> IdentityRegistry:
    return IdentityRegistry(
        (
            IdentityRecord("0101", "Alpha Institutional Securities Limited", "Alpha Inst", "P001", "Alpha Institutional Securities Limited", "Alpha Inst", 0.8, date(2020, 1, 1)),
            IdentityRecord("0102", "Broad Market Securities Limited", "Broad Market", "P002", "Broad Market Securities Limited", "Broad Market", 0.1, date(2020, 1, 1)),
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
                active_broker_code=broker,
                passive_broker_code="9999",
                trade_id=f"{symbol}-{second}",
                side_contract="synthetic_canonical",
                source="synthetic.hktransaction",
            )
            events.extend((book, trade))
    return events


def _feature_row(feature: FeatureSnapshot) -> dict[str, object]:
    flow = feature.flow_60s
    return {
        "dataset_mode": "synthetic_demo",
        "symbol": feature.symbol,
        "feature_ts": feature.as_of.isoformat(),
        "book_event_ts": feature.book_event_ts.isoformat(),
        "mid_price": feature.mid_price,
        "spread_bps": feature.spread_bps,
        "depth_l1": feature.depth_l1,
        "bid_depth_l5": feature.bid_depth_l5,
        "ask_depth_l5": feature.ask_depth_l5,
        "book_imbalance_l1": feature.book_imbalance_l1,
        "book_imbalance_l5": feature.book_imbalance_l5,
        "microprice_edge_bps": feature.microprice_edge_bps,
        "ofi_l1_normalized": feature.ofi_l1_normalized,
        "depth_recovery_ratio_60s": feature.depth_recovery_ratio_60s,
        "spread_recovery_ratio_60s": feature.spread_recovery_ratio_60s,
        "book_update_count_10s": feature.book_update_count_10s,
        "realized_mid_volatility_60s": feature.realized_mid_volatility_60s,
        "buy_turnover_60s": flow.buy_turnover,
        "sell_turnover_60s": flow.sell_turnover,
        "neutral_turnover_60s": flow.neutral_turnover,
        "signed_flow_ratio_60s": flow.signed_flow_ratio,
        "skill_weighted_flow_60s": flow.skill_weighted_flow,
        "broker_mapping_coverage": flow.broker_mapping_coverage,
        "participant_mapping_coverage": flow.participant_mapping_coverage,
        "top_broker_net_concentration": flow.top_broker_net_concentration,
        "mid_return_60s": feature.mid_return_60s,
        "flow_price_state": feature.flow_price_state.value,
        "liquidity_stress": feature.liquidity_stress,
        "smart_money_score": feature.smart_money_score,
        "confidence": feature.confidence,
        "complete": feature.complete,
        "sessionStart": feature.session_start.isoformat() if feature.session_start else "",
        "replayed": feature.replayed,
        "trade_eligible": feature.trade_eligible,
        "uses_future_data": False,
    }


def _label_row(label: MarkoutLabel) -> dict[str, object]:
    row = asdict(label)
    row["signal_ts"] = label.signal_ts.isoformat()
    row["label_ts"] = label.label_ts.isoformat()
    row["dataset_mode"] = "synthetic_demo"
    row["uses_future_data"] = True
    return row


def _write_csv(path: Path, rows: list[Mapping[str, object]], fieldnames: Iterable[str] | None = None) -> None:
    columns = list(fieldnames or (rows[0].keys() if rows else ()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _summaries(features: tuple[FeatureSnapshot, ...], labels: list[MarkoutLabel]) -> list[dict[str, object]]:
    feature_by_key = {(feature.symbol, feature.as_of): feature for feature in features}
    groups: dict[tuple[int, str], list[float]] = defaultdict(list)
    for label in labels:
        feature = feature_by_key[(label.symbol, label.signal_ts)]
        groups[(label.horizon_seconds, "all")].append(label.signed_markout)
        groups[(label.horizon_seconds, feature.flow_price_state.value)].append(label.signed_markout)
        if feature.trade_eligible:
            groups[(label.horizon_seconds, "eligible")].append(label.signed_markout)
    rows = []
    for (horizon, group), values in sorted(groups.items()):
        rows.append(
            {
                "dataset_mode": "synthetic_demo",
                "horizon_seconds": horizon,
                "group": group,
                "signal_count": len(values),
                "mean_signed_markout": fmean(values),
                "hit_rate": sum(value > 0 for value in values) / len(values),
            }
        )
    return rows


def _shock_rows(events: list[BookSnapshotEvent | TradeEvent]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    by_symbol: dict[str, list[MicrostructureObservation]] = defaultdict(list)
    for event in events:
        if isinstance(event, BookSnapshotEvent):
            mid = (event.bids[0].price + event.asks[0].price) / 2
            by_symbol[event.symbol].append(
                MicrostructureObservation(
                    event.event_ts,
                    mid,
                    (event.asks[0].price - event.bids[0].price) / mid * 10_000,
                    event.bids[0].size + event.asks[0].size,
                    0.0,
                    0.0,
                )
            )
    detector = ShockDetector(k=5.0, min_history=30)
    labeler = ShockLabeler(horizon_seconds=60)
    event_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    for symbol, observations in by_symbol.items():
        last_detection: datetime | None = None
        for index, observation in enumerate(observations):
            event = detector.detect(observations[: index + 1], as_of=observation.event_ts)
            if event is None or (last_detection and (event.detected_at - last_detection).total_seconds() < 60):
                continue
            last_detection = event.detected_at
            event_rows.append({"dataset_mode": "synthetic_demo", "symbol": symbol, **asdict(event)})
            try:
                outcome = labeler.label(event, observations)
            except ValueError:
                continue
            outcome_rows.append({"dataset_mode": "synthetic_demo", "symbol": symbol, **asdict(outcome)})
    for rows in (event_rows, outcome_rows):
        for row in rows:
            for key, value in tuple(row.items()):
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
                elif hasattr(value, "value"):
                    row[key] = value.value
    return event_rows, outcome_rows


def run_demo(output_dir: Path, *, duration_seconds: int = 720, seed: int = 7) -> dict[str, object]:
    if duration_seconds < 360:
        raise ValueError("duration_seconds must allow a five-minute markout")
    output_dir.mkdir(parents=True, exist_ok=True)
    events = _synthetic_events(duration_seconds, seed)
    engine = SmartMoneyEngine(identity_registry=_identity_registry())
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    last_signal_second = duration_seconds - 300
    snapshot_times = tuple(BASE + timedelta(seconds=second) for second in range(60, last_signal_second + 1, 10))
    features = ReplayRunner(engine).run(events, snapshot_times=snapshot_times)
    books = [event for event in events if isinstance(event, BookSnapshotEvent)]
    labeler = MarkoutLabeler()
    labels = [label for feature in features for label in labeler.label(feature, books)]
    feature_rows = [_feature_row(feature) for feature in features]
    label_rows = [_label_row(label) for label in labels]
    summary_rows = _summaries(features, labels)
    shock_events, shock_outcomes = _shock_rows(events)
    _write_csv(output_dir / "feature_snapshots.csv", feature_rows)
    _write_csv(output_dir / "markout_labels.csv", label_rows)
    _write_csv(output_dir / "backtest_summary.csv", summary_rows)
    _write_csv(output_dir / "shock_events.csv", shock_events)
    _write_csv(output_dir / "shock_outcomes.csv", shock_outcomes)
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
    parser = argparse.ArgumentParser(description="Run a deterministic synthetic smart-money microstructure replay")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/demo"))
    parser.add_argument("--duration-seconds", type=int, default=720)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(run_demo(args.output_dir, duration_seconds=args.duration_seconds, seed=args.seed), ensure_ascii=False))


if __name__ == "__main__":
    main()

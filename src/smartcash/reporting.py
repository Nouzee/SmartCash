from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Iterable, Mapping, Sequence

from .contracts import AggressorSide, BookSnapshotEvent, FeatureSnapshot, TradeEvent
from .replay import MarkoutLabel
from .shocks import MicrostructureObservation, ShockDetector, ShockLabeler


def feature_row(feature: FeatureSnapshot, *, dataset_mode: str) -> dict[str, object]:
    flow = feature.flow_60s
    return {
        "dataset_mode": dataset_mode,
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
        "seat_identity_coverage": flow.seat_identity_coverage,
        "broker_entity_mapping_coverage": flow.broker_entity_mapping_coverage,
        "top_seat_net_concentration": flow.top_seat_net_concentration,
        "top_broker_entity_net_concentration": flow.top_broker_entity_net_concentration,
        "mid_return_60s": feature.mid_return_60s,
        "flow_price_state": feature.flow_price_state.value,
        "liquidity_stress": feature.liquidity_stress,
        "smart_money_score": feature.smart_money_score,
        "confidence": feature.confidence,
        "complete": feature.complete,
        "complete_60s": feature.complete_60s,
        "complete_300s": feature.complete_300s,
        "sessionStart": feature.session_start.isoformat() if feature.session_start else "",
        "replayed": feature.replayed,
        "trade_eligible": feature.trade_eligible,
        "uses_future_data": False,
    }


def label_row(label: MarkoutLabel, *, dataset_mode: str) -> dict[str, object]:
    row = asdict(label)
    row["signal_ts"] = label.signal_ts.isoformat()
    row["label_ts"] = label.label_ts.isoformat()
    row["dataset_mode"] = dataset_mode
    row["uses_future_data"] = True
    return row


def write_csv(
    path: Path,
    rows: list[Mapping[str, object]],
    fieldnames: Iterable[str] | None = None,
) -> None:
    columns = list(fieldnames or (rows[0].keys() if rows else ()))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summary_rows(
    features: Sequence[FeatureSnapshot],
    labels: Sequence[MarkoutLabel],
    *,
    dataset_mode: str,
) -> list[dict[str, object]]:
    feature_by_key = {(feature.symbol, feature.as_of): feature for feature in features}
    groups: dict[tuple[int, str], list[float]] = defaultdict(list)
    for label in labels:
        feature = feature_by_key[(label.symbol, label.signal_ts)]
        groups[(label.horizon_seconds, "all")].append(label.signed_markout)
        groups[(label.horizon_seconds, feature.flow_price_state.value)].append(label.signed_markout)
        if feature.trade_eligible:
            groups[(label.horizon_seconds, "eligible")].append(label.signed_markout)
    return [
        {
            "dataset_mode": dataset_mode,
            "horizon_seconds": horizon,
            "group": group,
            "signal_count": len(values),
            "mean_signed_markout": fmean(values),
            "hit_rate": sum(value > 0 for value in values) / len(values),
        }
        for (horizon, group), values in sorted(groups.items())
    ]


def shock_rows(
    events: Sequence[BookSnapshotEvent | TradeEvent],
    *,
    dataset_mode: str,
    features: Sequence[FeatureSnapshot] = (),
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    books_by_symbol: dict[str, list[BookSnapshotEvent]] = defaultdict(list)
    trades_by_symbol: dict[str, list[TradeEvent]] = defaultdict(list)
    for event in events:
        if isinstance(event, BookSnapshotEvent):
            books_by_symbol[event.symbol].append(event)
        else:
            trades_by_symbol[event.symbol].append(event)
    detector = ShockDetector(k=5.0, min_history=30)
    labeler = ShockLabeler(horizon_seconds=60)
    features_by_symbol: dict[str, list[FeatureSnapshot]] = defaultdict(list)
    for feature in features:
        features_by_symbol[feature.symbol].append(feature)
    for symbol in features_by_symbol:
        features_by_symbol[symbol].sort(key=lambda item: item.as_of)
    event_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    for symbol, books in books_by_symbol.items():
        books = sorted(books, key=lambda item: item.event_ts)
        observations: list[MicrostructureObservation] = []
        trades = sorted(trades_by_symbol.get(symbol, []), key=lambda item: item.event_ts)
        trade_cursor = 0
        feature_cursor = 0
        symbol_features = features_by_symbol.get(symbol, [])
        latest_feature: FeatureSnapshot | None = None
        previous_book_ts: datetime | None = None
        for book in books:
            buy = 0.0
            sell = 0.0
            while trade_cursor < len(trades) and trades[trade_cursor].event_ts <= book.event_ts:
                trade = trades[trade_cursor]
                if previous_book_ts is None or trade.event_ts > previous_book_ts:
                    if trade.aggressor_side is AggressorSide.BUY:
                        buy += trade.turnover
                    elif trade.aggressor_side is AggressorSide.SELL:
                        sell += trade.turnover
                trade_cursor += 1
            while feature_cursor < len(symbol_features) and symbol_features[feature_cursor].as_of <= book.event_ts:
                latest_feature = symbol_features[feature_cursor]
                feature_cursor += 1
            directional = buy + sell
            signed_flow = (buy - sell) / directional if directional else 0.0
            mid = (book.bids[0].price + book.asks[0].price) / 2
            observations.append(
                MicrostructureObservation(
                    book.event_ts,
                    mid,
                    (book.asks[0].price - book.bids[0].price) / mid * 10_000,
                    book.bids[0].size + book.asks[0].size,
                    signed_flow,
                    latest_feature.smart_money_score if latest_feature is not None else 0.0,
                )
            )
            previous_book_ts = book.event_ts
        last_detection: datetime | None = None
        for index, observation in enumerate(observations):
            event = detector.detect(observations[: index + 1], as_of=observation.event_ts)
            if event is None or (last_detection and (event.detected_at - last_detection).total_seconds() < 60):
                continue
            last_detection = event.detected_at
            event_rows.append({"dataset_mode": dataset_mode, "symbol": symbol, **asdict(event)})
            try:
                outcome = labeler.label(event, observations)
            except ValueError:
                continue
            outcome_rows.append({"dataset_mode": dataset_mode, "symbol": symbol, **asdict(outcome)})
    for rows in (event_rows, outcome_rows):
        for row in rows:
            for key, value in tuple(row.items()):
                if isinstance(value, datetime):
                    row[key] = value.isoformat()
                elif hasattr(value, "value"):
                    row[key] = value.value
    return event_rows, outcome_rows

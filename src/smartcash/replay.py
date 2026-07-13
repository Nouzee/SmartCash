from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from .contracts import BookSnapshotEvent, FeatureSnapshot, MicrostructureStepSnapshot, TradeEvent
from .engine import SmartCashEngine

MarketEvent = BookSnapshotEvent | TradeEvent


class ReplayRunner:
    """Deterministic event-time replay; no wall-clock or future-data access."""

    def __init__(self, engine: SmartCashEngine) -> None:
        self.engine = engine

    def run(
        self,
        events: Sequence[MarketEvent],
        *,
        snapshot_times: Sequence[datetime],
    ) -> tuple[FeatureSnapshot, ...]:
        ordered_events = list(events)
        if any(current.captured_at < previous.captured_at for previous, current in zip(ordered_events, ordered_events[1:], strict=False)):
            raise ValueError("replay events must be non-decreasing by captured_at")
        ordered_times = tuple(snapshot_times)
        if any(current <= previous for previous, current in zip(ordered_times, ordered_times[1:], strict=False)):
            raise ValueError("snapshot_times must be strictly increasing")
        cursor = 0
        active_symbols: set[str] = set()
        features: list[FeatureSnapshot] = []
        for snapshot_ts in ordered_times:
            while cursor < len(ordered_events) and ordered_events[cursor].captured_at <= snapshot_ts:
                event = ordered_events[cursor]
                self.engine.ingest(event)
                active_symbols.add(event.symbol)
                cursor += 1
            for symbol in sorted(active_symbols):
                try:
                    features.append(self.engine.snapshot(symbol, snapshot_ts))
                except LookupError:
                    continue
        return tuple(features)

    def run_steps(
        self,
        events: Sequence[MarketEvent],
        *,
        checkpoint_times: Sequence[datetime],
    ) -> tuple[MicrostructureStepSnapshot, ...]:
        ordered_events = list(events)
        if any(
            current.captured_at < previous.captured_at
            for previous, current in zip(ordered_events, ordered_events[1:], strict=False)
        ):
            raise ValueError("replay events must be non-decreasing by captured_at")
        ordered_times = tuple(checkpoint_times)
        if any(
            current <= previous
            for previous, current in zip(ordered_times, ordered_times[1:], strict=False)
        ):
            raise ValueError("checkpoint_times must be strictly increasing")
        cursor = 0
        active_symbols: set[str] = set()
        steps: list[MicrostructureStepSnapshot] = []
        for checkpoint in ordered_times:
            while cursor < len(ordered_events) and ordered_events[cursor].captured_at <= checkpoint:
                event = ordered_events[cursor]
                self.engine.ingest(event)
                active_symbols.add(event.symbol)
                cursor += 1
            for symbol in sorted(active_symbols):
                try:
                    steps.append(self.engine.step_snapshot(symbol, checkpoint))
                except LookupError:
                    continue
        return tuple(steps)


@dataclass(frozen=True, slots=True)
class MarkoutLabel:
    symbol: str
    signal_ts: datetime
    label_ts: datetime
    horizon_seconds: int
    direction: int
    raw_mid_return: float
    signed_markout: float


class MarkoutLabeler:
    """Offline-only future midpoint labels for frozen feature snapshots."""

    def __init__(
        self,
        *,
        horizons_seconds: tuple[int, ...] = (10, 30, 60, 300),
        max_lag_seconds: float = 2.0,
    ) -> None:
        if not horizons_seconds or any(horizon <= 0 for horizon in horizons_seconds) or max_lag_seconds < 0:
            raise ValueError("markout horizons must be positive")
        self.horizons_seconds = tuple(sorted(set(horizons_seconds)))
        self.max_lag_seconds = max_lag_seconds

    def label(
        self,
        feature: FeatureSnapshot,
        books: Sequence[BookSnapshotEvent],
    ) -> tuple[MarkoutLabel, ...]:
        symbol_books = sorted(
            (book for book in books if book.symbol == feature.symbol and book.event_ts >= feature.as_of),
            key=lambda book: book.event_ts,
        )
        direction = 1 if feature.smart_money_score > 0 else -1 if feature.smart_money_score < 0 else 0
        labels: list[MarkoutLabel] = []
        for horizon in self.horizons_seconds:
            target = feature.as_of + timedelta(seconds=horizon)
            latest = target + timedelta(seconds=self.max_lag_seconds)
            future = next((book for book in symbol_books if target <= book.event_ts <= latest), None)
            if future is None:
                continue
            future_mid = (future.bids[0].price + future.asks[0].price) / 2
            raw_return = future_mid / feature.mid_price - 1
            labels.append(
                MarkoutLabel(
                    symbol=feature.symbol,
                    signal_ts=feature.as_of,
                    label_ts=future.event_ts,
                    horizon_seconds=horizon,
                    direction=direction,
                    raw_mid_return=raw_return,
                    signed_markout=direction * raw_return,
                )
            )
        return tuple(labels)

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from smartcash import SNAPSHOT_SCHEMA_VERSION
from smartcash.contracts import (
    AggressorSide,
    BookLevel,
    BookSnapshotEvent,
    MicrostructureStepSnapshot,
    SessionContext,
    TradeEvent,
)
from smartcash.engine import SmartCashEngine
from smartcash.replay import ReplayRunner


BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def test_replay_emits_dual_plane_snapshot_only_after_events_arrive() -> None:
    first_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1),
        captured_at=BASE + timedelta(seconds=1, milliseconds=100),
        bids=(BookLevel(100.0, 1_000),),
        asks=(BookLevel(100.2, 800),),
        source="xtquant.l2thousand",
    )
    trade = TradeEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1, milliseconds=50),
        captured_at=BASE + timedelta(seconds=1, milliseconds=200),
        price=100.2,
        volume=100,
        turnover=10_020.0,
        aggressor_side=AggressorSide.BUY,
        active_seat_code="0101",
        passive_seat_code="0202",
        trade_id="trade-1",
        side_contract="verified",
    )
    late_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=2),
        captured_at=BASE + timedelta(seconds=3, milliseconds=100),
        bids=(BookLevel(100.1, 900),),
        asks=(BookLevel(100.3, 700),),
        source="xtquant.l2thousand",
    )
    engine = SmartCashEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))

    steps = ReplayRunner(engine).run_steps(
        (first_book, trade, late_book),
        checkpoint_times=(BASE + timedelta(seconds=2), BASE + timedelta(seconds=4)),
    )

    assert len(steps) == 2
    assert all(isinstance(step, MicrostructureStepSnapshot) for step in steps)
    assert steps[0].schema_version == SNAPSHOT_SCHEMA_VERSION
    assert steps[0].decision_state.feature.book_event_ts == first_book.event_ts
    assert steps[0].execution_state.bids == first_book.bids
    assert steps[0].execution_state.asks == first_book.asks
    assert steps[0].execution_state.last_trade == trade
    assert steps[0].source_watermark.book_captured_at == first_book.captured_at
    assert steps[0].source_watermark.trade_id == "trade-1"
    assert steps[1].execution_state.bids == late_book.bids
    assert steps[1].source_watermark.book_captured_at == late_book.captured_at


def test_engine_does_not_backdate_a_late_book_into_an_earlier_step() -> None:
    first_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1),
        captured_at=BASE + timedelta(seconds=1),
        bids=(BookLevel(100.0, 1_000),),
        asks=(BookLevel(100.2, 800),),
        source="xtquant.l2thousand",
    )
    late_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=2),
        captured_at=BASE + timedelta(seconds=3),
        bids=(BookLevel(99.0, 1_000),),
        asks=(BookLevel(99.2, 800),),
        source="xtquant.l2thousand",
    )
    engine = SmartCashEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    engine.ingest(first_book)
    engine.ingest(late_book)

    step = engine.step_snapshot("00700.HK", BASE + timedelta(seconds=2))

    assert step.decision_state.feature.book_event_ts == first_book.event_ts
    assert step.execution_state.bids == first_book.bids


def test_late_stale_book_is_audited_but_does_not_replace_newer_exchange_state() -> None:
    current_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=2),
        captured_at=BASE + timedelta(seconds=2),
        bids=(BookLevel(100.0, 1_000),),
        asks=(BookLevel(100.2, 800),),
        source="xtquant.l2thousand",
    )
    late_stale_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1),
        captured_at=BASE + timedelta(seconds=3),
        bids=(BookLevel(99.0, 1_000),),
        asks=(BookLevel(99.2, 800),),
        source="xtquant.l2thousand",
    )
    engine = SmartCashEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))

    steps = ReplayRunner(engine).run_steps(
        (current_book, late_stale_book),
        checkpoint_times=(BASE + timedelta(seconds=4),),
    )

    assert steps[0].decision_state.feature.book_event_ts == current_book.event_ts
    assert steps[0].execution_state.bids == current_book.bids


def test_dual_plane_snapshot_rejects_a_mismatched_source_watermark() -> None:
    book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1),
        captured_at=BASE + timedelta(seconds=1),
        bids=(BookLevel(100.0, 1_000),),
        asks=(BookLevel(100.2, 800),),
        source="xtquant.l2thousand",
    )
    engine = SmartCashEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    engine.ingest(book)
    step = engine.step_snapshot("00700.HK", BASE + timedelta(seconds=2))
    mismatched = replace(
        step.source_watermark,
        book_captured_at=BASE + timedelta(seconds=1, milliseconds=1),
    )

    with pytest.raises(ValueError, match="watermark"):
        replace(step, source_watermark=mismatched)


def test_negative_latency_book_cannot_split_decision_and_execution_planes() -> None:
    current_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1),
        captured_at=BASE + timedelta(seconds=1),
        bids=(BookLevel(100.0, 1_000),),
        asks=(BookLevel(100.2, 800),),
        source="xtquant.l2thousand",
    )
    future_exchange_book = BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=10),
        captured_at=BASE + timedelta(seconds=2),
        bids=(BookLevel(101.0, 1_000),),
        asks=(BookLevel(101.2, 800),),
        source="xtquant.l2thousand",
    )
    engine = SmartCashEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    engine.ingest(current_book)
    engine.ingest(future_exchange_book)

    step = engine.step_snapshot("00700.HK", BASE + timedelta(seconds=3))

    assert step.decision_state.feature.book_event_ts == current_book.event_ts
    assert step.execution_state.book_event_ts == current_book.event_ts

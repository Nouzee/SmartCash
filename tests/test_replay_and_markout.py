from datetime import datetime, timedelta

import pytest

from smartcash.contracts import AggressorSide, BookLevel, BookSnapshotEvent, SessionContext, TradeEvent
from smartcash.engine import SmartMoneyEngine
from smartcash.identity import IdentityRecord, IdentityRegistry
from smartcash.replay import MarkoutLabeler, ReplayRunner
from smartcash.reporting import feature_row


BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def book(seconds: int, bid: float, ask: float, bid_size: int = 100, ask_size: int = 100) -> BookSnapshotEvent:
    return BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=seconds),
        bids=(BookLevel(bid, bid_size),),
        asks=(BookLevel(ask, ask_size),),
        source="xtquant.l2thousand",
    )


def test_future_events_do_not_change_past_replay_snapshot() -> None:
    identity = IdentityRecord(
        seat_code="0101",
        seat_full_name="Seat 0101",
        seat_display_name="0101",
        broker_entity_id="broker-alpha",
        broker_entity_full_name="Alpha Limited",
        broker_entity_display_name="Alpha",
        external_aliases=(),
        skill_score=1.0,
        effective_from=BASE.date(),
    )

    def run(events):
        engine = SmartMoneyEngine(identity_registry=IdentityRegistry((identity,)))
        engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
        return ReplayRunner(engine).run(events, snapshot_times=(BASE + timedelta(seconds=2),))[0]

    trade = TradeEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=1),
        price=100.1,
        volume=1_000,
        turnover=100_100,
        aggressor_side=AggressorSide.BUY,
        active_seat_code="0101",
        passive_seat_code="9999",
        trade_id="1",
        side_contract="canonical",
    )
    causal = [book(0, 100.0, 100.2), trade, book(2, 100.1, 100.3, 200, 50)]
    future = book(20, 99.0, 99.2)

    assert run(causal) == run(causal + [future])


def test_markout_is_a_separate_future_label() -> None:
    engine = SmartMoneyEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    feature = ReplayRunner(engine).run(
        [book(0, 100.0, 100.2), book(2, 100.1, 100.3, 200, 50)],
        snapshot_times=(BASE + timedelta(seconds=2),),
    )[0]
    future_books = [book(2, 100.1, 100.3), book(12, 100.4, 100.6)]

    label = MarkoutLabeler(horizons_seconds=(10,)).label(feature, future_books)[0]

    assert label.horizon_seconds == 10
    assert label.raw_mid_return == pytest.approx(100.5 / 100.2 - 1)
    assert label.direction == 1
    assert label.signed_markout == pytest.approx(label.raw_mid_return)
    assert label.label_ts == BASE + timedelta(seconds=12)

    row = feature_row(feature, dataset_mode="historical_replay")
    assert row["dataset_mode"] == "historical_replay"
    assert row["complete_60s"] is False
    assert row["complete_300s"] is False


def test_markout_does_not_use_a_stale_book_as_a_fixed_horizon_label() -> None:
    engine = SmartMoneyEngine()
    engine.set_session(SessionContext(BASE.date(), BASE, BASE, True))
    feature = ReplayRunner(engine).run(
        [book(0, 100.0, 100.2), book(2, 100.1, 100.3, 200, 50)],
        snapshot_times=(BASE + timedelta(seconds=2),),
    )[0]

    labels = MarkoutLabeler(horizons_seconds=(10,), max_lag_seconds=2).label(
        feature,
        [book(2, 100.1, 100.3), book(30, 100.4, 100.6)],
    )

    assert labels == ()

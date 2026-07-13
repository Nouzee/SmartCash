from datetime import date, datetime, timedelta

from smartcash.contracts import (
    AggressorSide,
    BookLevel,
    BookSnapshotEvent,
    FlowPriceState,
    SessionContext,
    TradeEvent,
)
from smartcash.engine import SmartMoneyEngine
from smartcash.identity import IdentityRecord, IdentityRegistry


BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def engine() -> SmartMoneyEngine:
    registry = IdentityRegistry(
        (
            IdentityRecord("0101", "Alpha Limited", "Alpha", "P1", "Alpha Limited", "Alpha", 1.0, date(2020, 1, 1)),
        )
    )
    result = SmartMoneyEngine(identity_registry=registry)
    window_start = BASE - timedelta(seconds=300)
    result.set_session(SessionContext(BASE.date(), window_start, window_start, True, True))
    return result


def book(seconds: int, mid: float) -> BookSnapshotEvent:
    return BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=seconds),
        bids=(BookLevel(mid - 0.05, 200),),
        asks=(BookLevel(mid + 0.05, 50),),
        source="xtquant.l2thousand",
    )


def buy(seconds: int) -> TradeEvent:
    return TradeEvent(
        "00700.HK", BASE + timedelta(seconds=seconds), 100.0, 1_000, 100_000,
        AggressorSide.BUY, "0101", "9999", str(seconds), "canonical",
    )


def test_strong_flow_without_price_response_is_only_absorption_candidate() -> None:
    subject = engine()
    subject.ingest(book(0, 100.0))
    subject.ingest(buy(59))
    subject.ingest(book(60, 100.0))

    feature = subject.snapshot("00700.HK", BASE + timedelta(seconds=60))

    assert feature.flow_price_state is FlowPriceState.ABSORPTION_CANDIDATE
    assert not feature.trade_eligible


def test_strong_flow_with_same_direction_price_response_is_confirmed() -> None:
    subject = engine()
    subject.ingest(book(0, 100.0))
    subject.ingest(buy(59))
    subject.ingest(book(60, 100.2))

    feature = subject.snapshot("00700.HK", BASE + timedelta(seconds=60))

    assert feature.flow_price_state is FlowPriceState.CONFIRMED
    assert feature.mid_return_60s > 0
    assert feature.trade_eligible

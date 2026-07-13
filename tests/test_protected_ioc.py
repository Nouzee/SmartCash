from datetime import datetime, timedelta

from smartcash.contracts import BookLevel, BookSnapshotEvent, SessionContext
from smartcash.engine import SmartCashEngine
from smartcash.execution import (
    ExecutionCapacity,
    IocExecutionStatus,
    OrderSide,
    PointInTimeInstrumentRules,
    ProtectedIocExecutor,
    ProtectedIocOrder,
)


BASE = datetime.fromisoformat("2026-01-05T10:00:00+08:00")
OPEN = datetime.fromisoformat("2026-01-05T09:30:00+08:00")
CAPACITY = ExecutionCapacity(available_cash_hkd=100_000.0, sellable_quantity=0)


def _step(
    *,
    captured_at: datetime,
    coverage_complete: bool = True,
    bids: tuple[BookLevel, ...] | None = None,
    asks: tuple[BookLevel, ...] | None = None,
):
    engine = SmartCashEngine()
    engine.set_session(
        SessionContext(BASE.date(), OPEN, OPEN, True, coverage_complete=coverage_complete)
    )
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=captured_at,
            captured_at=captured_at,
            bids=bids or (
                BookLevel(99.9, 10_000),
                BookLevel(99.8, 10_000),
            ),
            asks=asks or (
                BookLevel(100.1, 10_000),
                BookLevel(100.2, 10_000),
            ),
            source="xtquant.l2thousand",
        )
    )
    return engine.step_snapshot("00700.HK", captured_at)


def _buy_order(*, eligible_from: datetime) -> ProtectedIocOrder:
    return ProtectedIocOrder(
        order_id="candidate-1-entry",
        symbol="00700.HK",
        side=OrderSide.BUY,
        quantity=1_000,
        decision_midpoint=100.0,
        decision_time=BASE,
        eligible_from=eligible_from,
        expires_at=eligible_from + timedelta(seconds=5),
    )


def test_protected_ioc_uses_execution_book_and_stricter_price_guard() -> None:
    eligible_from = BASE + timedelta(seconds=1)
    step = _step(captured_at=eligible_from)
    rules = PointInTimeInstrumentRules(
        symbol="00700.HK",
        effective_at=BASE,
        board_lot=100,
        tick_size=0.01,
    )

    result = ProtectedIocExecutor().execute(
        _buy_order(eligible_from=eligible_from), step, rules, CAPACITY
    )

    # The 10 bp decision-mid guard is 100.10 and is stricter than two ticks
    # beyond the best ask (100.12), so the second ask must not be consumed.
    assert result.status is IocExecutionStatus.PARTIALLY_FILLED
    assert result.filled_quantity == 400
    assert result.cancelled_quantity == 600
    assert result.vwap == 100.1
    assert result.price_limit == 100.1
    assert result.fills[0].book_captured_at == eligible_from
    assert result.fills[0].level == 1


def test_protected_ioc_waits_for_a_book_captured_after_eligibility() -> None:
    eligible_from = BASE + timedelta(seconds=2)
    stale_step = _step(captured_at=BASE + timedelta(seconds=1))
    rules = PointInTimeInstrumentRules(
        symbol="00700.HK",
        effective_at=BASE,
        board_lot=100,
        tick_size=0.01,
    )

    result = ProtectedIocExecutor().execute(
        _buy_order(eligible_from=eligible_from), stale_step, rules, CAPACITY
    )

    assert result.status is IocExecutionStatus.WAITING_FOR_NEW_BOOK
    assert result.filled_quantity == 0
    assert result.cancelled_quantity == 0


def test_protected_ioc_rejects_rules_that_were_not_effective_at_decision_time() -> None:
    eligible_from = BASE + timedelta(seconds=1)
    step = _step(captured_at=eligible_from)
    future_rules = PointInTimeInstrumentRules(
        symbol="00700.HK",
        effective_at=BASE + timedelta(seconds=1),
        board_lot=100,
        tick_size=0.01,
    )

    result = ProtectedIocExecutor().execute(
        _buy_order(eligible_from=eligible_from),
        step,
        future_rules,
        CAPACITY,
    )

    assert result.status is IocExecutionStatus.INVALID_POINT_IN_TIME_RULES
    assert result.filled_quantity == 0


def test_protected_ioc_waits_for_quality_and_can_only_terminate_once() -> None:
    eligible_from = BASE + timedelta(seconds=1)
    incomplete = _step(captured_at=eligible_from, coverage_complete=False)
    complete = _step(captured_at=eligible_from + timedelta(seconds=1))
    rules = PointInTimeInstrumentRules(
        symbol="00700.HK",
        effective_at=OPEN,
        board_lot=100,
        tick_size=0.01,
    )
    executor = ProtectedIocExecutor()
    order = _buy_order(eligible_from=eligible_from)

    waiting = executor.execute(order, incomplete, rules, CAPACITY)
    filled = executor.execute(order, complete, rules, CAPACITY)
    repeated = executor.execute(order, complete, rules, CAPACITY)

    assert waiting.status is IocExecutionStatus.WAITING_FOR_QUALITY_BOOK
    assert filled.status is IocExecutionStatus.PARTIALLY_FILLED
    assert repeated.status is IocExecutionStatus.ALREADY_TERMINAL
    assert repeated.fills == ()


def test_capacity_uses_notional_cash_and_one_aggregate_board_lot_rounding() -> None:
    eligible_from = BASE + timedelta(seconds=1)
    rules = PointInTimeInstrumentRules(
        symbol="00700.HK",
        effective_at=OPEN,
        board_lot=100,
        tick_size=0.01,
    )
    cash_limited = ProtectedIocExecutor().execute(
        _buy_order(eligible_from=eligible_from),
        _step(captured_at=eligible_from),
        rules,
        ExecutionCapacity(available_cash_hkd=15_000.0, sellable_quantity=0),
    )
    two_odd_levels = ProtectedIocOrder(
        order_id="candidate-2-entry",
        symbol="00700.HK",
        side=OrderSide.BUY,
        quantity=100,
        decision_midpoint=100.0,
        decision_time=BASE,
        eligible_from=eligible_from,
        expires_at=eligible_from + timedelta(seconds=5),
        visible_participation=1.0,
    )
    aggregate_lot = ProtectedIocExecutor().execute(
        two_odd_levels,
        _step(
            captured_at=eligible_from,
            asks=(BookLevel(100.05, 50), BookLevel(100.06, 50)),
        ),
        rules,
        CAPACITY,
    )

    assert cash_limited.filled_quantity == 100
    assert cash_limited.capacity_notional_hkd == 15_000.0
    assert aggregate_lot.status is IocExecutionStatus.FILLED
    assert aggregate_lot.filled_quantity == 100
    assert tuple(fill.quantity for fill in aggregate_lot.fills) == (50, 50)

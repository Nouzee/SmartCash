"""Causal taker-only execution primitives for SmartCash research.

The executor consumes only the execution plane of a step snapshot.  It never
infers fills from decision features, future replenishment, or broker queues.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from .contracts import BookLevel, MicrostructureStepSnapshot


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class IocExecutionStatus(StrEnum):
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    UNFILLED_PRICE_PROTECTION = "unfilled_price_protection"
    UNFILLED_CAPACITY = "unfilled_capacity"
    WAITING_FOR_NEW_BOOK = "waiting_for_new_book"
    WAITING_FOR_QUALITY_BOOK = "waiting_for_quality_book"
    EXPIRED = "expired"
    INVALID_POINT_IN_TIME_RULES = "invalid_point_in_time_rules"
    ALREADY_TERMINAL = "already_terminal"


@dataclass(frozen=True, slots=True)
class PointInTimeInstrumentRules:
    symbol: str
    effective_at: datetime
    board_lot: int
    tick_size: float
    effective_to: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.effective_at.tzinfo is None:
            raise ValueError("effective_at must be timezone-aware")
        if self.board_lot <= 0:
            raise ValueError("board_lot must be positive")
        if not isfinite(self.tick_size) or self.tick_size <= 0:
            raise ValueError("tick_size must be finite and positive")
        if self.effective_to is not None:
            if self.effective_to.tzinfo is None:
                raise ValueError("effective_to must be timezone-aware")
            if self.effective_to < self.effective_at:
                raise ValueError("effective_to must not precede effective_at")


@dataclass(frozen=True, slots=True)
class ExecutionCapacity:
    available_cash_hkd: float
    sellable_quantity: int

    def __post_init__(self) -> None:
        if not isfinite(self.available_cash_hkd) or self.available_cash_hkd < 0:
            raise ValueError("available_cash_hkd must be finite and non-negative")
        if self.sellable_quantity < 0:
            raise ValueError("sellable_quantity must be non-negative")


@dataclass(frozen=True, slots=True)
class ProtectedIocOrder:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    decision_midpoint: float
    decision_time: datetime
    eligible_from: datetime
    expires_at: datetime
    max_sweep_bps: float = 10.0
    max_ticks_beyond_best: int = 2
    visible_participation: float = 0.02
    max_levels: int = 5
    target_notional_hkd: float = 50_000.0

    def __post_init__(self) -> None:
        if not self.order_id or not self.symbol:
            raise ValueError("order_id and symbol are required")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not isfinite(self.decision_midpoint) or self.decision_midpoint <= 0:
            raise ValueError("decision_midpoint must be finite and positive")
        if any(ts.tzinfo is None for ts in (self.decision_time, self.eligible_from, self.expires_at)):
            raise ValueError("order timestamps must be timezone-aware")
        if self.decision_time > self.eligible_from or self.eligible_from > self.expires_at:
            raise ValueError("order timestamps must be decision <= eligible <= expiry")
        if not isfinite(self.max_sweep_bps) or self.max_sweep_bps < 0:
            raise ValueError("max_sweep_bps must be finite and non-negative")
        if self.max_ticks_beyond_best < 0:
            raise ValueError("max_ticks_beyond_best must be non-negative")
        if not 0 < self.visible_participation <= 1:
            raise ValueError("visible_participation must be in (0, 1]")
        if not 1 <= self.max_levels <= 5:
            raise ValueError("max_levels must be between 1 and 5")
        if not isfinite(self.target_notional_hkd) or self.target_notional_hkd <= 0:
            raise ValueError("target_notional_hkd must be finite and positive")


@dataclass(frozen=True, slots=True)
class IocFill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    level: int
    book_event_ts: datetime
    book_captured_at: datetime


@dataclass(frozen=True, slots=True)
class IocExecutionResult:
    run_id: str
    order_id: str
    status: IocExecutionStatus
    requested_quantity: int
    filled_quantity: int
    cancelled_quantity: int
    vwap: float | None
    price_limit: float | None
    fills: tuple[IocFill, ...]
    execution_book_event_ts: datetime | None
    execution_book_captured_at: datetime | None
    capacity_notional_hkd: float | None
    capacity_quantity: int | None


class ProtectedIocExecutor:
    """Run-scoped sweep simulator with explicit price/capacity guards."""

    def __init__(self, *, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id is required")
        self.run_id = run_id
        self._terminal_order_ids: set[str] = set()

    def execute(
        self,
        order: ProtectedIocOrder,
        step: MicrostructureStepSnapshot,
        rules: PointInTimeInstrumentRules,
        capacity: ExecutionCapacity,
    ) -> IocExecutionResult:
        if order.symbol != step.symbol or order.symbol != rules.symbol:
            raise ValueError("order, snapshot, and instrument-rule symbols must match")
        if order.order_id in self._terminal_order_ids:
            return self._empty(order, IocExecutionStatus.ALREADY_TERMINAL)
        if rules.effective_at > order.decision_time or (
            rules.effective_to is not None and order.decision_time > rules.effective_to
        ):
            return self._terminal(
                self._empty(order, IocExecutionStatus.INVALID_POINT_IN_TIME_RULES)
            )
        if step.as_of > order.expires_at:
            return self._terminal(
                self._empty(
                    order,
                    IocExecutionStatus.EXPIRED,
                    cancelled_quantity=order.quantity,
                )
            )

        execution = step.execution_state
        if (
            execution.book_captured_at < order.eligible_from
            or execution.book_captured_at <= order.decision_time
        ):
            return self._empty(order, IocExecutionStatus.WAITING_FOR_NEW_BOOK)
        if not step.complete:
            return self._empty(order, IocExecutionStatus.WAITING_FOR_QUALITY_BOOK)

        levels = execution.asks if order.side is OrderSide.BUY else execution.bids
        levels = levels[: order.max_levels]
        price_limit = self._price_limit(order, levels[0], rules)
        visible_notional = sum(level.price * level.size for level in levels)
        capacity_notional = min(
            order.target_notional_hkd,
            visible_notional * order.visible_participation,
        )
        if order.side is OrderSide.BUY:
            capacity_notional = min(capacity_notional, capacity.available_cash_hkd)
            portfolio_quantity = order.quantity
        else:
            portfolio_quantity = capacity.sellable_quantity
        notional_quantity = int(capacity_notional / levels[0].price)
        executable_quantity = min(order.quantity, notional_quantity, portfolio_quantity)
        executable_quantity -= executable_quantity % rules.board_lot
        while (
            executable_quantity > 0
            and self._displayed_notional(levels, executable_quantity) > capacity_notional
        ):
            executable_quantity -= rules.board_lot
        if executable_quantity <= 0:
            return self._terminal(
                self._empty(
                    order,
                    IocExecutionStatus.UNFILLED_CAPACITY,
                    cancelled_quantity=order.quantity,
                    price_limit=price_limit,
                    book_event_ts=execution.book_event_ts,
                    book_captured_at=execution.book_captured_at,
                    capacity_notional_hkd=capacity_notional,
                    capacity_quantity=executable_quantity,
                )
            )

        remaining = executable_quantity
        fills: list[IocFill] = []
        for level_number, level in enumerate(levels, start=1):
            if not self._within_price_limit(order.side, level.price, price_limit):
                break
            fill_quantity = min(remaining, level.size)
            if fill_quantity <= 0:
                continue
            fills.append(
                IocFill(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=fill_quantity,
                    price=level.price,
                    level=level_number,
                    book_event_ts=execution.book_event_ts,
                    book_captured_at=execution.book_captured_at,
                )
            )
            remaining -= fill_quantity
            if remaining == 0:
                break

        filled_quantity = sum(fill.quantity for fill in fills)
        if filled_quantity == 0:
            return self._terminal(
                self._empty(
                    order,
                    IocExecutionStatus.UNFILLED_PRICE_PROTECTION,
                    cancelled_quantity=order.quantity,
                    price_limit=price_limit,
                    book_event_ts=execution.book_event_ts,
                    book_captured_at=execution.book_captured_at,
                    capacity_notional_hkd=capacity_notional,
                    capacity_quantity=executable_quantity,
                )
            )

        vwap = sum(fill.quantity * fill.price for fill in fills) / filled_quantity
        status = (
            IocExecutionStatus.FILLED
            if filled_quantity == order.quantity
            else IocExecutionStatus.PARTIALLY_FILLED
        )
        return self._terminal(
            IocExecutionResult(
                run_id=self.run_id,
                order_id=order.order_id,
                status=status,
                requested_quantity=order.quantity,
                filled_quantity=filled_quantity,
                cancelled_quantity=order.quantity - filled_quantity,
                vwap=vwap,
                price_limit=price_limit,
                fills=tuple(fills),
                execution_book_event_ts=execution.book_event_ts,
                execution_book_captured_at=execution.book_captured_at,
                capacity_notional_hkd=capacity_notional,
                capacity_quantity=executable_quantity,
            )
        )

    def _terminal(self, result: IocExecutionResult) -> IocExecutionResult:
        self._terminal_order_ids.add(result.order_id)
        return result

    @staticmethod
    def _price_limit(
        order: ProtectedIocOrder,
        best_opposite: BookLevel,
        rules: PointInTimeInstrumentRules,
    ) -> float:
        midpoint = Decimal(str(order.decision_midpoint))
        sweep_fraction = Decimal(str(order.max_sweep_bps)) / Decimal("10000")
        best = Decimal(str(best_opposite.price))
        ticks = Decimal(order.max_ticks_beyond_best) * Decimal(str(rules.tick_size))
        if order.side is OrderSide.BUY:
            limit = min(midpoint * (Decimal(1) + sweep_fraction), best + ticks)
        else:
            limit = max(midpoint * (Decimal(1) - sweep_fraction), best - ticks)
        return float(limit)

    @staticmethod
    def _within_price_limit(side: OrderSide, price: float, price_limit: float) -> bool:
        price_decimal = Decimal(str(price))
        limit_decimal = Decimal(str(price_limit))
        return price_decimal <= limit_decimal if side is OrderSide.BUY else price_decimal >= limit_decimal

    @staticmethod
    def _displayed_notional(levels: tuple[BookLevel, ...], quantity: int) -> float:
        remaining = quantity
        notional = Decimal(0)
        for level in levels:
            level_quantity = min(remaining, level.size)
            notional += Decimal(level_quantity) * Decimal(str(level.price))
            remaining -= level_quantity
            if remaining == 0:
                break
        return float(notional) if remaining == 0 else float("inf")

    def _empty(
        self,
        order: ProtectedIocOrder,
        status: IocExecutionStatus,
        *,
        cancelled_quantity: int = 0,
        price_limit: float | None = None,
        book_event_ts: datetime | None = None,
        book_captured_at: datetime | None = None,
        capacity_notional_hkd: float | None = None,
        capacity_quantity: int | None = None,
    ) -> IocExecutionResult:
        return IocExecutionResult(
            run_id=self.run_id,
            order_id=order.order_id,
            status=status,
            requested_quantity=order.quantity,
            filled_quantity=0,
            cancelled_quantity=cancelled_quantity,
            vwap=None,
            price_limit=price_limit,
            fills=(),
            execution_book_event_ts=book_event_ts,
            execution_book_captured_at=book_captured_at,
            capacity_notional_hkd=capacity_notional_hkd,
            capacity_quantity=capacity_quantity,
        )

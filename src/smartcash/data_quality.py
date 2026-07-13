from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from math import inf
from typing import Sequence

from .contracts import AggressorSide, BookSnapshotEvent, TradeEvent
from .identity import IdentityRegistry

MarketEvent = BookSnapshotEvent | TradeEvent


@dataclass(frozen=True, slots=True)
class SymbolTapeAudit:
    symbol: str
    trade_count: int
    sequence_present: bool
    out_of_order_count: int
    duplicate_trade_id_count: int
    sequence_gap_count: int
    arrival_timestamp_count: int
    stale_trade_count: int
    negative_arrival_latency_count: int
    arrival_out_of_order_count: int
    max_arrival_latency_ms: float

    @property
    def arrival_timestamp_coverage(self) -> float:
        return self.arrival_timestamp_count / self.trade_count if self.trade_count else 0.0

    @property
    def tape_complete(self) -> bool:
        return bool(
            self.trade_count
            and self.sequence_present
            and not self.out_of_order_count
            and not self.duplicate_trade_id_count
            and not self.sequence_gap_count
            and self.arrival_timestamp_coverage == 1.0
            and not self.stale_trade_count
            and not self.negative_arrival_latency_count
            and not self.arrival_out_of_order_count
        )


@dataclass(frozen=True, slots=True)
class TapeAudit:
    symbols: tuple[SymbolTapeAudit, ...]

    def for_symbol(self, symbol: str) -> SymbolTapeAudit | None:
        return next((item for item in self.symbols if item.symbol == symbol), None)

    @property
    def trade_count(self) -> int:
        return sum(item.trade_count for item in self.symbols)

    @property
    def sequence_present(self) -> bool:
        return bool(self.symbols) and all(item.sequence_present for item in self.symbols)

    @property
    def out_of_order_count(self) -> int:
        return sum(item.out_of_order_count for item in self.symbols)

    @property
    def duplicate_trade_id_count(self) -> int:
        return sum(item.duplicate_trade_id_count for item in self.symbols)

    @property
    def sequence_gap_count(self) -> int:
        return sum(item.sequence_gap_count for item in self.symbols)

    @property
    def tape_complete(self) -> bool:
        return bool(self.symbols) and all(item.tape_complete for item in self.symbols)


@dataclass(frozen=True, slots=True)
class SymbolTradeCaptureAudit:
    symbol: str
    source: str
    subscription_acknowledged: bool
    subscribed_at: datetime | None
    first_heartbeat_at: datetime | None
    last_heartbeat_at: datetime | None
    heartbeat_count: int
    max_heartbeat_gap_seconds: float
    dropped_callback_count: int
    expected_open: datetime | None = None
    expected_end: datetime | None = None
    heartbeat_ordered: bool = True

    @property
    def capture_complete(self) -> bool:
        return bool(
            self.source == "xtquant.hktransaction"
            and self.subscription_acknowledged
            and self.subscribed_at is not None
            and self.expected_open is not None
            and self.expected_end is not None
            and self.subscribed_at <= self.expected_open
            and self.first_heartbeat_at is not None
            and self.first_heartbeat_at <= self.expected_open
            and self.last_heartbeat_at is not None
            and self.last_heartbeat_at >= self.expected_end
            and self.heartbeat_count >= 2
            and self.heartbeat_ordered
            and self.max_heartbeat_gap_seconds <= 60.0
            and not self.dropped_callback_count
        )


@dataclass(frozen=True, slots=True)
class TradeCaptureAudit:
    symbols: tuple[SymbolTradeCaptureAudit, ...]

    def for_symbol(self, symbol: str) -> SymbolTradeCaptureAudit | None:
        return next((item for item in self.symbols if item.symbol == symbol), None)


@dataclass(slots=True)
class _MutableTapeState:
    trade_count: int = 0
    sequence_present: bool = True
    last_event_ts: datetime | None = None
    last_sequence: int | None = None
    out_of_order_count: int = 0
    duplicate_trade_id_count: int = 0
    sequence_gap_count: int = 0
    arrival_timestamp_count: int = 0
    stale_trade_count: int = 0
    negative_arrival_latency_count: int = 0
    arrival_out_of_order_count: int = 0
    max_arrival_latency_ms: float = 0.0
    last_captured_at: datetime | None = None
    trade_ids: set[str] = field(default_factory=set)


class TapeAuditor:
    """Audit raw file order before events are sorted for deterministic replay."""

    def __init__(self, *, max_arrival_latency_ms: float = 1_000.0) -> None:
        if not 0 <= max_arrival_latency_ms <= 1_000.0:
            raise ValueError("max_arrival_latency_ms must be in [0, 1000] for Phase 0 acceptance")
        self.max_arrival_latency_ms = max_arrival_latency_ms
        self._states: dict[str, _MutableTapeState] = {}

    def record(
        self,
        event: TradeEvent,
        *,
        raw_sequence: object,
        captured_at: datetime | None,
    ) -> None:
        state = self._states.setdefault(event.symbol, _MutableTapeState())
        if state.last_event_ts is not None and event.event_ts < state.last_event_ts:
            state.out_of_order_count += 1
        state.last_event_ts = event.event_ts
        if event.trade_id:
            if event.trade_id in state.trade_ids:
                state.duplicate_trade_id_count += 1
            state.trade_ids.add(event.trade_id)
        try:
            sequence = int(raw_sequence)
        except (TypeError, ValueError):
            state.sequence_present = False
        else:
            if state.last_sequence is not None and sequence != state.last_sequence + 1:
                state.sequence_gap_count += 1
            state.last_sequence = sequence
        if captured_at is not None:
            state.arrival_timestamp_count += 1
            if state.last_captured_at is not None and captured_at < state.last_captured_at:
                state.arrival_out_of_order_count += 1
            state.last_captured_at = captured_at
            latency_ms = (captured_at - event.event_ts).total_seconds() * 1_000
            if latency_ms < 0:
                state.negative_arrival_latency_count += 1
            else:
                state.max_arrival_latency_ms = max(state.max_arrival_latency_ms, latency_ms)
                if latency_ms > self.max_arrival_latency_ms:
                    state.stale_trade_count += 1
        state.trade_count += 1

    def snapshot(self) -> TapeAudit:
        return TapeAudit(
            tuple(
                SymbolTapeAudit(
                    symbol=symbol,
                    trade_count=state.trade_count,
                    sequence_present=state.sequence_present,
                    out_of_order_count=state.out_of_order_count,
                    duplicate_trade_id_count=state.duplicate_trade_id_count,
                    sequence_gap_count=state.sequence_gap_count,
                    arrival_timestamp_count=state.arrival_timestamp_count,
                    stale_trade_count=state.stale_trade_count,
                    negative_arrival_latency_count=state.negative_arrival_latency_count,
                    arrival_out_of_order_count=state.arrival_out_of_order_count,
                    max_arrival_latency_ms=state.max_arrival_latency_ms,
                )
                for symbol, state in sorted(self._states.items())
            )
        )


@dataclass(frozen=True, slots=True)
class SymbolBookInputAudit:
    symbol: str
    valid_book_count: int
    arrival_timestamp_count: int
    rejected_crossed_locked_count: int
    rejected_invalid_count: int
    stale_book_count: int
    event_out_of_order_count: int
    arrival_out_of_order_count: int
    negative_arrival_latency_count: int
    max_arrival_latency_ms: float

    @property
    def arrival_timestamp_coverage(self) -> float:
        return self.arrival_timestamp_count / self.valid_book_count if self.valid_book_count else 0.0

    @property
    def input_complete(self) -> bool:
        return bool(
            self.valid_book_count
            and self.arrival_timestamp_coverage == 1.0
            and not self.rejected_crossed_locked_count
            and not self.rejected_invalid_count
            and not self.stale_book_count
            and not self.event_out_of_order_count
            and not self.arrival_out_of_order_count
            and not self.negative_arrival_latency_count
        )


@dataclass(frozen=True, slots=True)
class BookInputAudit:
    symbols: tuple[SymbolBookInputAudit, ...]

    def for_symbol(self, symbol: str) -> SymbolBookInputAudit | None:
        return next((item for item in self.symbols if item.symbol == symbol), None)


@dataclass(slots=True)
class _MutableBookInputState:
    valid_book_count: int = 0
    arrival_timestamp_count: int = 0
    rejected_crossed_locked_count: int = 0
    rejected_invalid_count: int = 0
    stale_book_count: int = 0
    event_out_of_order_count: int = 0
    arrival_out_of_order_count: int = 0
    negative_arrival_latency_count: int = 0
    max_arrival_latency_ms: float = 0.0
    last_event_ts: datetime | None = None
    last_captured_at: datetime | None = None


class BookInputAuditor:
    def __init__(self, *, max_arrival_latency_ms: float = 1_000.0) -> None:
        if not 0 <= max_arrival_latency_ms <= 1_000.0:
            raise ValueError("max_arrival_latency_ms must be in [0, 1000] for Phase 0 acceptance")
        self.max_arrival_latency_ms = max_arrival_latency_ms
        self._states: dict[str, _MutableBookInputState] = {}

    def record_valid(self, event: BookSnapshotEvent, *, captured_at: datetime | None) -> None:
        state = self._states.setdefault(event.symbol, _MutableBookInputState())
        state.valid_book_count += 1
        if state.last_event_ts is not None and event.event_ts < state.last_event_ts:
            state.event_out_of_order_count += 1
        state.last_event_ts = event.event_ts
        if captured_at is None:
            return
        state.arrival_timestamp_count += 1
        if state.last_captured_at is not None and captured_at < state.last_captured_at:
            state.arrival_out_of_order_count += 1
        state.last_captured_at = captured_at
        latency_ms = (captured_at - event.event_ts).total_seconds() * 1_000
        if latency_ms < 0:
            state.negative_arrival_latency_count += 1
        else:
            state.max_arrival_latency_ms = max(state.max_arrival_latency_ms, latency_ms)
            if latency_ms > self.max_arrival_latency_ms:
                state.stale_book_count += 1

    def record_rejection(self, symbol: str, error: ValueError) -> None:
        state = self._states.setdefault(symbol, _MutableBookInputState())
        if "crossed or locked" in str(error):
            state.rejected_crossed_locked_count += 1
        else:
            state.rejected_invalid_count += 1

    def snapshot(self) -> BookInputAudit:
        return BookInputAudit(
            tuple(
                SymbolBookInputAudit(
                    symbol=symbol,
                    valid_book_count=state.valid_book_count,
                    arrival_timestamp_count=state.arrival_timestamp_count,
                    rejected_crossed_locked_count=state.rejected_crossed_locked_count,
                    rejected_invalid_count=state.rejected_invalid_count,
                    stale_book_count=state.stale_book_count,
                    event_out_of_order_count=state.event_out_of_order_count,
                    arrival_out_of_order_count=state.arrival_out_of_order_count,
                    negative_arrival_latency_count=state.negative_arrival_latency_count,
                    max_arrival_latency_ms=state.max_arrival_latency_ms,
                )
                for symbol, state in sorted(self._states.items())
            )
        )


@dataclass(frozen=True, slots=True)
class SymbolDataQuality:
    symbol: str
    first_event_ts: datetime | None
    last_event_ts: datetime | None
    trade_count: int
    book_count: int
    sequence_present: bool
    out_of_order_count: int
    duplicate_trade_id_count: int
    sequence_gap_count: int
    trade_arrival_timestamp_coverage: float
    stale_trade_count: int
    negative_trade_arrival_latency_count: int
    trade_arrival_out_of_order_count: int
    max_trade_arrival_latency_ms: float
    trade_capture_source: str
    trade_subscription_acknowledged: bool
    trade_subscribed_at: datetime | None
    trade_first_heartbeat_at: datetime | None
    trade_last_heartbeat_at: datetime | None
    trade_heartbeat_count: int
    max_trade_heartbeat_gap_seconds: float
    dropped_trade_callback_count: int
    trade_capture_complete: bool
    max_book_gap_seconds: float
    active_session_seconds: float
    book_arrival_timestamp_coverage: float
    rejected_crossed_locked_count: int
    rejected_invalid_book_count: int
    stale_book_count: int
    book_event_out_of_order_count: int
    book_arrival_out_of_order_count: int
    negative_book_arrival_latency_count: int
    max_book_arrival_latency_ms: float
    directional_turnover: float
    neutral_turnover: float
    neutral_share: float
    active_broker_disclosure_coverage: float
    broker_mapping_coverage: float
    participant_mapping_coverage: float
    tape_complete: bool
    book_input_complete: bool
    book_coverage_complete: bool
    session_duration_complete: bool
    combined_complete: bool
    trade_sources: tuple[str, ...]
    book_sources: tuple[str, ...]
    side_contracts: tuple[str, ...]

    def to_row(self) -> dict[str, object]:
        row = asdict(self)
        row["first_event_ts"] = self.first_event_ts.isoformat() if self.first_event_ts else ""
        row["last_event_ts"] = self.last_event_ts.isoformat() if self.last_event_ts else ""
        row["trade_subscribed_at"] = (
            self.trade_subscribed_at.isoformat() if self.trade_subscribed_at else ""
        )
        row["trade_first_heartbeat_at"] = (
            self.trade_first_heartbeat_at.isoformat() if self.trade_first_heartbeat_at else ""
        )
        row["trade_last_heartbeat_at"] = (
            self.trade_last_heartbeat_at.isoformat() if self.trade_last_heartbeat_at else ""
        )
        row["trade_sources"] = "|".join(self.trade_sources)
        row["book_sources"] = "|".join(self.book_sources)
        row["side_contracts"] = "|".join(self.side_contracts)
        return row


def build_data_quality_rows(
    events: Sequence[MarketEvent],
    *,
    tape_audit: TapeAudit,
    book_input_audit: BookInputAudit,
    expected_open: datetime,
    expected_end: datetime,
    expected_symbols: Sequence[str],
    max_book_gap_seconds: float,
    trade_capture_audit: TradeCaptureAudit | None = None,
    identity_registry: IdentityRegistry | None = None,
) -> tuple[SymbolDataQuality, ...]:
    if not 0 < max_book_gap_seconds <= 5.0:
        raise ValueError("max_book_gap_seconds must be in (0, 5] for Phase 0 acceptance")
    active_session_seconds = expected_hk_active_session_seconds(expected_open, expected_end)
    session_duration_complete = True
    expected_symbol_set = {symbol.strip() for symbol in expected_symbols if symbol.strip()}
    if not expected_symbol_set:
        raise ValueError("expected_symbols must contain at least one symbol")
    audited_symbols = {
        *(item.symbol for item in tape_audit.symbols),
        *(item.symbol for item in book_input_audit.symbols),
        *(item.symbol for item in (trade_capture_audit or TradeCaptureAudit(())).symbols),
    }
    unexpected_audited_symbols = audited_symbols - expected_symbol_set
    if unexpected_audited_symbols:
        raise ValueError(
            f"audited symbols are not in expected_symbols: {sorted(unexpected_audited_symbols)}"
        )
    registry = identity_registry or IdentityRegistry()
    capture_audit = trade_capture_audit or TradeCaptureAudit(())
    events_by_symbol: dict[str, list[MarketEvent]] = defaultdict(list)
    for event in events:
        if event.symbol not in expected_symbol_set:
            raise ValueError(f"unexpected symbol {event.symbol!r} is not in expected_symbols")
        events_by_symbol[event.symbol].append(event)
    rows: list[SymbolDataQuality] = []
    for symbol in sorted(expected_symbol_set):
        symbol_events = events_by_symbol[symbol]
        trades = [event for event in symbol_events if isinstance(event, TradeEvent)]
        books = sorted(
            (event for event in symbol_events if isinstance(event, BookSnapshotEvent)),
            key=lambda item: item.event_ts,
        )
        directional_turnover = sum(
            event.turnover for event in trades if event.aggressor_side is not AggressorSide.NEUTRAL
        )
        neutral_turnover = sum(
            event.turnover for event in trades if event.aggressor_side is AggressorSide.NEUTRAL
        )
        disclosed_turnover = 0.0
        broker_mapped_turnover = 0.0
        participant_mapped_turnover = 0.0
        for trade in trades:
            if trade.aggressor_side is AggressorSide.NEUTRAL:
                continue
            if trade.active_broker_code:
                disclosed_turnover += trade.turnover
            identity = registry.resolve(trade.active_broker_code, trade.event_ts.date())
            if identity is not None:
                broker_mapped_turnover += trade.turnover
                if identity.participant_id:
                    participant_mapped_turnover += trade.turnover
        if books:
            book_gaps = [
                max(0.0, (books[0].event_ts - expected_open).total_seconds()),
                *(
                    active_hk_seconds_between(previous.event_ts, current.event_ts)
                    for previous, current in zip(books, books[1:], strict=False)
                ),
                active_hk_seconds_between(books[-1].event_ts, expected_end),
            ]
            largest_book_gap = max(book_gaps)
            book_complete = largest_book_gap <= max_book_gap_seconds
        else:
            largest_book_gap = inf
            book_complete = False
        symbol_audit = tape_audit.for_symbol(symbol)
        symbol_capture_audit = capture_audit.for_symbol(symbol)
        book_audit = book_input_audit.for_symbol(symbol)
        tape_complete = symbol_audit.tape_complete if symbol_audit is not None else False
        trade_capture_complete = (
            symbol_capture_audit.capture_complete if symbol_capture_audit is not None else False
        )
        book_input_complete = book_audit.input_complete if book_audit is not None else False
        total_turnover = directional_turnover + neutral_turnover
        rows.append(
            SymbolDataQuality(
                symbol=symbol,
                first_event_ts=min((event.event_ts for event in symbol_events), default=None),
                last_event_ts=max((event.event_ts for event in symbol_events), default=None),
                trade_count=len(trades),
                book_count=len(books),
                sequence_present=symbol_audit.sequence_present if symbol_audit is not None else False,
                out_of_order_count=symbol_audit.out_of_order_count if symbol_audit is not None else 0,
                duplicate_trade_id_count=(
                    symbol_audit.duplicate_trade_id_count if symbol_audit is not None else 0
                ),
                sequence_gap_count=symbol_audit.sequence_gap_count if symbol_audit is not None else 0,
                trade_arrival_timestamp_coverage=(
                    symbol_audit.arrival_timestamp_coverage if symbol_audit else 0.0
                ),
                stale_trade_count=symbol_audit.stale_trade_count if symbol_audit else 0,
                negative_trade_arrival_latency_count=(
                    symbol_audit.negative_arrival_latency_count if symbol_audit else 0
                ),
                trade_arrival_out_of_order_count=(
                    symbol_audit.arrival_out_of_order_count if symbol_audit else 0
                ),
                max_trade_arrival_latency_ms=(
                    symbol_audit.max_arrival_latency_ms if symbol_audit else 0.0
                ),
                trade_capture_source=(symbol_capture_audit.source if symbol_capture_audit else ""),
                trade_subscription_acknowledged=(
                    symbol_capture_audit.subscription_acknowledged
                    if symbol_capture_audit
                    else False
                ),
                trade_subscribed_at=(
                    symbol_capture_audit.subscribed_at if symbol_capture_audit else None
                ),
                trade_first_heartbeat_at=(
                    symbol_capture_audit.first_heartbeat_at if symbol_capture_audit else None
                ),
                trade_last_heartbeat_at=(
                    symbol_capture_audit.last_heartbeat_at if symbol_capture_audit else None
                ),
                trade_heartbeat_count=(
                    symbol_capture_audit.heartbeat_count if symbol_capture_audit else 0
                ),
                max_trade_heartbeat_gap_seconds=(
                    symbol_capture_audit.max_heartbeat_gap_seconds
                    if symbol_capture_audit
                    else inf
                ),
                dropped_trade_callback_count=(
                    symbol_capture_audit.dropped_callback_count if symbol_capture_audit else 0
                ),
                trade_capture_complete=trade_capture_complete,
                max_book_gap_seconds=largest_book_gap,
                active_session_seconds=active_session_seconds,
                book_arrival_timestamp_coverage=(
                    book_audit.arrival_timestamp_coverage if book_audit else 0.0
                ),
                rejected_crossed_locked_count=(
                    book_audit.rejected_crossed_locked_count if book_audit else 0
                ),
                rejected_invalid_book_count=(
                    book_audit.rejected_invalid_count if book_audit else 0
                ),
                stale_book_count=(book_audit.stale_book_count if book_audit else 0),
                book_event_out_of_order_count=(
                    book_audit.event_out_of_order_count if book_audit else 0
                ),
                book_arrival_out_of_order_count=(
                    book_audit.arrival_out_of_order_count if book_audit else 0
                ),
                negative_book_arrival_latency_count=(
                    book_audit.negative_arrival_latency_count if book_audit else 0
                ),
                max_book_arrival_latency_ms=(
                    book_audit.max_arrival_latency_ms if book_audit else 0.0
                ),
                directional_turnover=directional_turnover,
                neutral_turnover=neutral_turnover,
                neutral_share=neutral_turnover / total_turnover if total_turnover else 0.0,
                active_broker_disclosure_coverage=(
                    disclosed_turnover / directional_turnover if directional_turnover else 0.0
                ),
                broker_mapping_coverage=(
                    broker_mapped_turnover / directional_turnover if directional_turnover else 0.0
                ),
                participant_mapping_coverage=(
                    participant_mapped_turnover / directional_turnover if directional_turnover else 0.0
                ),
                tape_complete=tape_complete,
                book_input_complete=book_input_complete,
                book_coverage_complete=book_complete,
                session_duration_complete=session_duration_complete,
                combined_complete=(
                    tape_complete
                    and trade_capture_complete
                    and book_input_complete
                    and book_complete
                    and session_duration_complete
                ),
                trade_sources=tuple(sorted({event.source for event in trades})),
                book_sources=tuple(sorted({event.source for event in books})),
                side_contracts=tuple(sorted({event.side_contract for event in trades})),
            )
        )
    return tuple(rows)


_SUPPORTED_HK_CALENDAR_YEARS = frozenset({2025, 2026})
_HK_MARKET_HOLIDAYS = frozenset(
    {
        date(2025, 1, 1),
        date(2025, 1, 29),
        date(2025, 1, 30),
        date(2025, 1, 31),
        date(2025, 4, 4),
        date(2025, 4, 18),
        date(2025, 4, 21),
        date(2025, 5, 1),
        date(2025, 5, 5),
        date(2025, 7, 1),
        date(2025, 10, 1),
        date(2025, 10, 7),
        date(2025, 10, 29),
        date(2025, 12, 25),
        date(2025, 12, 26),
        date(2026, 1, 1),
        date(2026, 2, 17),
        date(2026, 2, 18),
        date(2026, 2, 19),
        date(2026, 4, 3),
        date(2026, 4, 6),
        date(2026, 4, 7),
        date(2026, 5, 1),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 1),
        date(2026, 10, 1),
        date(2026, 10, 19),
        date(2026, 12, 25),
    }
)
_HK_HALF_DAYS = frozenset(
    {
        date(2025, 1, 28),
        date(2025, 12, 24),
        date(2025, 12, 31),
        date(2026, 2, 16),
        date(2026, 12, 24),
        date(2026, 12, 31),
    }
)


def expected_hk_active_session_seconds(expected_open: datetime, expected_end: datetime) -> float:
    """Validate the versioned HKEX continuous-session calendar used by Phase 0."""

    if expected_open.tzinfo is None or expected_end.tzinfo is None:
        raise ValueError("HKEX session contract requires timezone-aware timestamps")
    if expected_open.utcoffset() != timedelta(hours=8) or expected_end.utcoffset() != timedelta(
        hours=8
    ):
        raise ValueError("HKEX session contract requires Asia/Hong_Kong (+08:00)")
    if expected_open.date() != expected_end.date():
        raise ValueError("HKEX session contract must stay within one trade date")
    trade_date = expected_open.date()
    if trade_date.year not in _SUPPORTED_HK_CALENDAR_YEARS:
        raise ValueError(f"HKEX session calendar does not cover {trade_date.year}")
    if trade_date.weekday() >= 5 or trade_date in _HK_MARKET_HOLIDAYS:
        raise ValueError(f"HKEX session contract rejects closed market date {trade_date}")
    required_end = time(12, 0) if trade_date in _HK_HALF_DAYS else time(16, 0)
    if expected_open.timetz().replace(tzinfo=None) != time(9, 30) or expected_end.timetz().replace(
        tzinfo=None
    ) != required_end:
        raise ValueError(
            f"HKEX session contract requires 09:30-{required_end.isoformat(timespec='minutes')} "
            f"for {trade_date.isoformat()}"
        )
    return 9_000.0 if trade_date in _HK_HALF_DAYS else 19_800.0


def active_hk_seconds_between(previous: datetime, current: datetime) -> float:
    gap = (current - previous).total_seconds()
    if previous.date() != current.date():
        return gap
    lunch_start = datetime.combine(previous.date(), time(12, 0), tzinfo=previous.tzinfo)
    lunch_end = datetime.combine(previous.date(), time(13, 0), tzinfo=previous.tzinfo)
    overlap_start = max(previous, lunch_start)
    overlap_end = min(current, lunch_end)
    scheduled_break = max(0.0, (overlap_end - overlap_start).total_seconds())
    return max(0.0, gap - scheduled_break)

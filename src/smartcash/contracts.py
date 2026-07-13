from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from math import isfinite


SNAPSHOT_SCHEMA_VERSION = "1.0"


class AggressorSide(StrEnum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"

    @property
    def sign(self) -> int:
        return 1 if self is AggressorSide.BUY else -1 if self is AggressorSide.SELL else 0


class FlowPriceState(StrEnum):
    CONFIRMED = "confirmed"
    ABSORPTION_CANDIDATE = "absorption_candidate"
    CONFLICT = "conflict"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class TradeEvent:
    symbol: str
    event_ts: datetime
    price: float
    volume: int
    turnover: float
    aggressor_side: AggressorSide
    active_seat_code: str
    passive_seat_code: str
    trade_id: str
    side_contract: str
    source: str = "xtquant.hktransaction"
    captured_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol is required")
        if self.event_ts.tzinfo is None:
            raise ValueError("event_ts must be timezone-aware")
        if self.captured_at is None:
            object.__setattr__(self, "captured_at", self.event_ts)
        elif self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be finite and positive")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if not isfinite(self.turnover) or self.turnover < 0:
            raise ValueError("turnover must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: float
    size: int
    order_count: int | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.price) or self.price <= 0:
            raise ValueError("book price must be finite and positive")
        if self.size < 0:
            raise ValueError("book size must be non-negative")
        if self.order_count is not None and self.order_count < 0:
            raise ValueError("order_count must be non-negative")


@dataclass(frozen=True, slots=True)
class BookSnapshotEvent:
    symbol: str
    event_ts: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    source: str
    captured_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.event_ts.tzinfo is None:
            raise ValueError("event_ts must be timezone-aware")
        if self.captured_at is None:
            object.__setattr__(self, "captured_at", self.event_ts)
        elif self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if "l2thousand" not in self.source.lower():
            raise ValueError("BookSnapshotEvent requires an l2thousand source")
        if not self.bids or not self.asks:
            raise ValueError("both sides of the order book are required")
        if any(left.price <= right.price for left, right in zip(self.bids, self.bids[1:], strict=False)):
            raise ValueError("bids must be strictly descending")
        if any(left.price >= right.price for left, right in zip(self.asks, self.asks[1:], strict=False)):
            raise ValueError("asks must be strictly ascending")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("crossed or locked books are not accepted")


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    symbol: str
    as_of: datetime
    book_event_ts: datetime
    mid_price: float
    spread_bps: float
    book_imbalance_l1: float
    book_imbalance_l2: float
    book_imbalance_l5: float
    bid_depth_l5: int
    ask_depth_l5: int
    depth_l1: int
    microprice: float
    microprice_edge_bps: float
    ofi_l1: float
    ofi_l1_normalized: float
    depth_recovery_ratio_60s: float
    spread_recovery_ratio_60s: float
    book_update_count_10s: int
    realized_mid_volatility_60s: float
    bid_refill_proxy: int
    ask_refill_proxy: int
    mid_return_60s: float
    flow_price_state: FlowPriceState
    liquidity_stress: float
    flow_10s: "FlowWindowFeatures"
    flow_30s: "FlowWindowFeatures"
    flow_60s: "FlowWindowFeatures"
    flow_300s: "FlowWindowFeatures"
    smart_money_score: float
    confidence: float
    complete: bool
    complete_60s: bool
    complete_300s: bool
    session_start: datetime | None
    replayed: bool
    trade_eligible: bool


@dataclass(frozen=True, slots=True)
class DecisionState:
    feature: FeatureSnapshot


@dataclass(frozen=True, slots=True)
class ExecutionState:
    book_event_ts: datetime
    book_captured_at: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    last_trade: TradeEvent | None

    def __post_init__(self) -> None:
        if self.book_event_ts.tzinfo is None or self.book_captured_at.tzinfo is None:
            raise ValueError("execution timestamps must be timezone-aware")
        if not self.bids or not self.asks:
            raise ValueError("execution state requires both sides of the book")


@dataclass(frozen=True, slots=True)
class SourceWatermark:
    book_event_ts: datetime
    book_captured_at: datetime
    trade_event_ts: datetime | None
    trade_captured_at: datetime | None
    trade_id: str

    def __post_init__(self) -> None:
        if self.book_event_ts.tzinfo is None or self.book_captured_at.tzinfo is None:
            raise ValueError("book watermark timestamps must be timezone-aware")
        if (self.trade_event_ts is None) != (self.trade_captured_at is None):
            raise ValueError("trade watermark timestamps must both be present or absent")
        if self.trade_event_ts is not None and (
            self.trade_event_ts.tzinfo is None or self.trade_captured_at.tzinfo is None
        ):
            raise ValueError("trade watermark timestamps must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MicrostructureStepSnapshot:
    schema_version: str
    symbol: str
    as_of: datetime
    decision_state: DecisionState
    execution_state: ExecutionState
    source_watermark: SourceWatermark
    complete: bool

    def __post_init__(self) -> None:
        if self.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"unsupported snapshot schema version: {self.schema_version}")
        if self.as_of.tzinfo is None:
            raise ValueError("snapshot as_of must be timezone-aware")
        if self.decision_state.feature.symbol != self.symbol:
            raise ValueError("decision state symbol must match snapshot symbol")
        if self.decision_state.feature.as_of != self.as_of:
            raise ValueError("decision state as_of must match snapshot as_of")
        if self.execution_state.book_captured_at > self.as_of:
            raise ValueError("execution state cannot contain a future-arriving book")
        if (
            self.execution_state.last_trade is not None
            and self.execution_state.last_trade.captured_at > self.as_of
        ):
            raise ValueError("execution state cannot contain a future-arriving trade")


@dataclass(frozen=True, slots=True)
class SeatIdentityContribution:
    seat_code: str
    seat_full_name: str
    seat_display_name: str
    broker_entity_id: str
    broker_entity_full_name: str
    broker_entity_display_name: str
    net_turnover: float
    skill_score: float


@dataclass(frozen=True, slots=True)
class BrokerEntityContribution:
    broker_entity_id: str
    broker_entity_full_name: str
    broker_entity_display_name: str
    net_turnover: float
    skill_score: float


@dataclass(frozen=True, slots=True)
class FlowWindowFeatures:
    window_seconds: int
    buy_turnover: float
    sell_turnover: float
    neutral_turnover: float
    directional_flow_ratio: float
    signed_flow_ratio: float
    neutral_share: float
    seat_identity_coverage: float
    broker_entity_mapping_coverage: float
    skill_weighted_flow: float
    top_seat_net_concentration: float
    top_broker_entity_net_concentration: float
    top_seats: tuple[SeatIdentityContribution, ...]
    top_broker_entities: tuple[BrokerEntityContribution, ...]


@dataclass(frozen=True, slots=True)
class SessionContext:
    trade_date: date
    expected_open: datetime
    session_start: datetime
    replayed: bool
    coverage_complete: bool = False

    def __post_init__(self) -> None:
        if self.expected_open.tzinfo is None or self.session_start.tzinfo is None:
            raise ValueError("session timestamps must be timezone-aware")
        if self.expected_open.date() != self.trade_date or self.session_start.date() != self.trade_date:
            raise ValueError("session timestamps must belong to trade_date")

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .contracts import AggressorSide, BookLevel, BookSnapshotEvent, TradeEvent

HK_TZ = ZoneInfo("Asia/Hong_Kong")


class DirectionConvention(StrEnum):
    VENDOR_DOC = "xtquant_vendor_doc_dir_1_sell_2_buy"
    THOUSAND_LEGACY = "thousand_legacy_dir_1_buy_2_sell"


def _seat_code(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return str(value).strip()
    return "" if number <= 0 else str(number).zfill(4)


def _raw_value(raw: Mapping[str, Any], *names: str) -> object:
    for name in names:
        value = raw.get(name)
        if value not in (None, ""):
            return value
    return None


def _event_ts(value: object) -> datetime:
    try:
        timestamp_ms = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("hktransaction time must be epoch milliseconds") from error
    return datetime.fromtimestamp(timestamp_ms / 1_000, tz=timezone.utc).astimezone(HK_TZ)


def _side(value: object, convention: DirectionConvention) -> AggressorSide:
    try:
        direction = int(value)
    except (TypeError, ValueError):
        direction = 0
    if convention is DirectionConvention.VENDOR_DOC:
        return AggressorSide.SELL if direction == 1 else AggressorSide.BUY if direction == 2 else AggressorSide.NEUTRAL
    return AggressorSide.BUY if direction == 1 else AggressorSide.SELL if direction == 2 else AggressorSide.NEUTRAL


def normalize_hktransaction(
    *,
    symbol: str,
    raw: Mapping[str, Any],
    convention: DirectionConvention,
    captured_at: datetime | None = None,
) -> TradeEvent:
    """Normalize one raw XTQuant trade without inferring missing identities."""

    price = float(raw.get("price", raw.get("Price", 0.0)))
    volume = int(raw.get("volume", raw.get("Volume", 0)))
    turnover_value = raw.get("turnover", raw.get("Turnover"))
    turnover = float(turnover_value) if turnover_value is not None else price * volume
    trade_id_value = _raw_value(raw, "tradeID", "TradeID", "seq", "Seq")
    return TradeEvent(
        symbol=symbol,
        event_ts=_event_ts(raw.get("time", raw.get("Time"))),
        price=price,
        volume=volume,
        turnover=turnover,
        aggressor_side=_side(raw.get("dir", raw.get("Dir")), convention),
        active_seat_code=_seat_code(_raw_value(raw, "activeBrokerNo", "ActiveBrokerNo")),
        passive_seat_code=_seat_code(_raw_value(raw, "brokerNo", "BrokerNo")),
        trade_id="" if trade_id_value is None else str(trade_id_value),
        side_contract=convention.value,
        captured_at=captured_at,
    )


def _array(raw: Mapping[str, Any], *names: str) -> list[Any]:
    for name in names:
        value = raw.get(name)
        if isinstance(value, (list, tuple)):
            return list(value)
    return []


def _levels(prices: list[Any], sizes: list[Any]) -> tuple[BookLevel, ...]:
    if len(prices) != len(sizes):
        raise ValueError("L2 price and size arrays must have the same length")
    levels = []
    for raw_price, raw_size in zip(prices, sizes, strict=True):
        price = float(raw_price or 0)
        size = int(raw_size or 0)
        if price > 0:
            levels.append(BookLevel(price=price, size=size))
    return tuple(levels)


def normalize_l2thousand(
    *,
    symbol: str,
    raw: Mapping[str, Any],
    captured_at: datetime | None = None,
) -> BookSnapshotEvent:
    """Normalize one XTQuant full-depth snapshot; broker queues are not accepted."""

    return BookSnapshotEvent(
        symbol=symbol,
        event_ts=_event_ts(raw.get("time", raw.get("Time"))),
        bids=_levels(
            _array(raw, "bidPrice", "BidPrice"),
            _array(raw, "bidVolume", "BidVolume"),
        ),
        asks=_levels(
            _array(raw, "askPrice", "AskPrice"),
            _array(raw, "askVolume", "AskVolume"),
        ),
        source="xtquant.l2thousand",
        captured_at=captured_at,
    )

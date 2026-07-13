from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from math import tanh
from statistics import pstdev

from .contracts import (
    AggressorSide,
    BookSnapshotEvent,
    FeatureSnapshot,
    FlowPriceState,
    FlowWindowFeatures,
    IdentityContribution,
    SessionContext,
    TradeEvent,
)
from .identity import IdentityRecord, IdentityRegistry


def _imbalance(book: BookSnapshotEvent, levels: int) -> float:
    bid = sum(level.size for level in book.bids[:levels])
    ask = sum(level.size for level in book.asks[:levels])
    total = bid + ask
    return (bid - ask) / total if total else 0.0


def _ofi_l1(previous: BookSnapshotEvent, current: BookSnapshotEvent) -> float:
    previous_bid, current_bid = previous.bids[0], current.bids[0]
    previous_ask, current_ask = previous.asks[0], current.asks[0]
    bid_term = (current_bid.size if current_bid.price >= previous_bid.price else 0) - (
        previous_bid.size if current_bid.price <= previous_bid.price else 0
    )
    ask_term = -(current_ask.size if current_ask.price <= previous_ask.price else 0) + (
        previous_ask.size if current_ask.price >= previous_ask.price else 0
    )
    return float(bid_term + ask_term)


def _range_position(value: float, low: float, high: float) -> float:
    return (value - low) / (high - low) if high > low else 0.0


class SmartMoneyEngine:
    """In-memory causal state for research replay and shadow evaluation."""

    def __init__(self, *, identity_registry: IdentityRegistry | None = None) -> None:
        self._books: dict[str, list[BookSnapshotEvent]] = defaultdict(list)
        self._trades: dict[str, list[TradeEvent]] = defaultdict(list)
        self._sessions: dict[object, SessionContext] = {}
        self._identity_registry = identity_registry or IdentityRegistry()

    def set_session(self, context: SessionContext) -> None:
        self._sessions[context.trade_date] = context

    def ingest(self, event: BookSnapshotEvent | TradeEvent) -> None:
        if isinstance(event, BookSnapshotEvent):
            books = self._books[event.symbol]
            if books and event.event_ts < books[-1].event_ts:
                raise ValueError("book events must be non-decreasing per symbol")
            books.append(event)
        elif isinstance(event, TradeEvent):
            trades = self._trades[event.symbol]
            if trades and event.event_ts < trades[-1].event_ts:
                raise ValueError("trade events must be non-decreasing per symbol")
            trades.append(event)

    def _flow(self, symbol: str, as_of: datetime, seconds: int) -> FlowWindowFeatures:
        start = as_of - timedelta(seconds=seconds)
        trades = [trade for trade in self._trades.get(symbol, ()) if start < trade.event_ts <= as_of]
        buy = sum(trade.turnover for trade in trades if trade.aggressor_side is AggressorSide.BUY)
        sell = sum(trade.turnover for trade in trades if trade.aggressor_side is AggressorSide.SELL)
        neutral = sum(trade.turnover for trade in trades if trade.aggressor_side is AggressorSide.NEUTRAL)
        directional = buy + sell
        total = directional + neutral
        broker_net: dict[str, float] = defaultdict(float)
        participant_net: dict[str, float] = defaultdict(float)
        identities: dict[str, IdentityRecord] = {}
        mapped_broker_turnover = 0.0
        mapped_participant_turnover = 0.0
        skill_numerator = 0.0
        for trade in trades:
            if trade.aggressor_side is AggressorSide.NEUTRAL:
                continue
            identity = self._identity_registry.resolve(trade.active_broker_code, trade.event_ts.date())
            if identity is None:
                continue
            signed = trade.aggressor_side.sign * trade.turnover
            identities[identity.broker_code] = identity
            broker_net[identity.broker_code] += signed
            mapped_broker_turnover += trade.turnover
            skill_numerator += identity.skill_score * signed
            if identity.participant_id:
                participant_net[identity.participant_id] += signed
                mapped_participant_turnover += trade.turnover
        ranked = sorted(broker_net, key=lambda code: abs(broker_net[code]), reverse=True)
        top_brokers = tuple(
            IdentityContribution(
                broker_code=code,
                broker_full_name=identities[code].broker_full_name,
                broker_display_name=identities[code].broker_display_name,
                participant_id=identities[code].participant_id,
                participant_full_name=identities[code].participant_full_name,
                participant_display_name=identities[code].participant_display_name,
                net_turnover=broker_net[code],
                skill_score=identities[code].skill_score,
            )
            for code in ranked[:3]
        )
        return FlowWindowFeatures(
            window_seconds=seconds,
            buy_turnover=buy,
            sell_turnover=sell,
            neutral_turnover=neutral,
            directional_flow_ratio=buy / directional if directional else 0.5,
            signed_flow_ratio=(buy - sell) / directional if directional else 0.0,
            neutral_share=neutral / total if total else 0.0,
            broker_mapping_coverage=mapped_broker_turnover / directional if directional else 0.0,
            participant_mapping_coverage=mapped_participant_turnover / directional if directional else 0.0,
            skill_weighted_flow=skill_numerator / directional if directional else 0.0,
            top_broker_net_concentration=abs(broker_net[ranked[0]]) / directional if ranked and directional else 0.0,
            top_participant_net_concentration=max(map(abs, participant_net.values()), default=0.0) / directional if directional else 0.0,
            top_brokers=top_brokers,
        )

    def snapshot(self, symbol: str, as_of: datetime) -> FeatureSnapshot:
        books = self._books.get(symbol, [])
        index = bisect_right([book.event_ts for book in books], as_of) - 1
        if index < 0:
            raise LookupError(f"no l2 book at or before {as_of.isoformat()} for {symbol}")
        book = books[index]
        causal_60s = [
            candidate
            for candidate in books[: index + 1]
            if candidate.event_ts >= as_of - timedelta(seconds=60)
        ]
        best_bid, best_ask = book.bids[0], book.asks[0]
        mid = (best_bid.price + best_ask.price) / 2
        microprice = (best_ask.price * best_bid.size + best_bid.price * best_ask.size) / (
            best_bid.size + best_ask.size
        ) if best_bid.size + best_ask.size else mid
        ofi = _ofi_l1(books[index - 1], book) if index > 0 else 0.0
        if index > 0:
            previous_depth = books[index - 1].bids[0].size + books[index - 1].asks[0].size
            current_depth = best_bid.size + best_ask.size
            average_depth = (previous_depth + current_depth) / 2
        else:
            average_depth = best_bid.size + best_ask.size
        flow_10s = self._flow(symbol, as_of, 10)
        flow_30s = self._flow(symbol, as_of, 30)
        flow_60s = self._flow(symbol, as_of, 60)
        flow_300s = self._flow(symbol, as_of, 300)
        session = self._sessions.get(as_of.date())
        session_coverage_ready = bool(
            session
            and session.coverage_complete
            and (session.replayed or session.session_start <= session.expected_open + timedelta(minutes=1))
        )
        elapsed_from_open = as_of - session.expected_open if session else timedelta(0)
        complete_60s = session_coverage_ready and elapsed_from_open >= timedelta(seconds=60)
        complete_300s = session_coverage_ready and elapsed_from_open >= timedelta(seconds=300)
        complete = complete_300s
        mapping_confidence = min(flow_60s.broker_mapping_coverage, flow_60s.participant_mapping_coverage)
        freshness_seconds = max(0.0, (as_of - book.event_ts).total_seconds())
        freshness_confidence = max(0.0, 1.0 - freshness_seconds / 10.0)
        confidence = min(mapping_confidence, freshness_confidence) if complete else 0.0
        imbalance = _imbalance(book, 1)
        microprice_edge_bps = (microprice / mid - 1) * 10_000
        ofi_normalized = ofi / average_depth if average_depth else 0.0
        spreads = [
            (candidate.asks[0].price - candidate.bids[0].price)
            / ((candidate.asks[0].price + candidate.bids[0].price) / 2)
            * 10_000
            for candidate in causal_60s
        ]
        depths = [candidate.bids[0].size + candidate.asks[0].size for candidate in causal_60s]
        mids = [(candidate.bids[0].price + candidate.asks[0].price) / 2 for candidate in causal_60s]
        mid_returns = [current / previous - 1 for previous, current in zip(mids, mids[1:], strict=False)]
        current_depth = best_bid.size + best_ask.size
        current_spread = spreads[-1]
        depth_recovery = _range_position(current_depth, min(depths), max(depths))
        spread_recovery = (max(spreads) - current_spread) / (max(spreads) - min(spreads)) if max(spreads) > min(spreads) else 0.0
        previous_book = books[index - 1] if index > 0 else None
        bid_refill = (
            max(0, best_bid.size - previous_book.bids[0].size)
            if previous_book is not None and best_bid.price == previous_book.bids[0].price
            else 0
        )
        ask_refill = (
            max(0, best_ask.size - previous_book.asks[0].size)
            if previous_book is not None and best_ask.price == previous_book.asks[0].price
            else 0
        )
        score = (
            0.25 * imbalance
            + 0.20 * tanh(microprice_edge_bps / 2.0)
            + 0.20 * max(-1.0, min(1.0, ofi_normalized))
            + 0.20 * flow_60s.signed_flow_ratio
            + 0.15 * flow_60s.skill_weighted_flow
        )
        mid_return_60s = mids[-1] / mids[0] - 1 if len(mids) > 1 else 0.0
        aligned_response_bps = (1 if flow_60s.signed_flow_ratio > 0 else -1) * mid_return_60s * 10_000
        if abs(flow_60s.signed_flow_ratio) < 0.20:
            flow_price_state = FlowPriceState.NEUTRAL
        elif aligned_response_bps >= 5.0:
            flow_price_state = FlowPriceState.CONFIRMED
        elif aligned_response_bps <= -5.0:
            flow_price_state = FlowPriceState.CONFLICT
        else:
            flow_price_state = FlowPriceState.ABSORPTION_CANDIDATE
        initial_spread = spreads[0]
        initial_depth = depths[0]
        liquidity_stress = max(0.0, current_spread / initial_spread - 1.0) if initial_spread else 0.0
        if initial_depth:
            liquidity_stress += max(0.0, 1.0 - current_depth / initial_depth)
        return FeatureSnapshot(
            symbol=symbol,
            as_of=as_of,
            book_event_ts=book.event_ts,
            mid_price=mid,
            spread_bps=(best_ask.price - best_bid.price) / mid * 10_000,
            book_imbalance_l1=_imbalance(book, 1),
            book_imbalance_l2=_imbalance(book, 2),
            book_imbalance_l5=_imbalance(book, 5),
            bid_depth_l5=sum(level.size for level in book.bids[:5]),
            ask_depth_l5=sum(level.size for level in book.asks[:5]),
            depth_l1=current_depth,
            microprice=microprice,
            microprice_edge_bps=microprice_edge_bps,
            ofi_l1=ofi,
            ofi_l1_normalized=ofi_normalized,
            depth_recovery_ratio_60s=depth_recovery,
            spread_recovery_ratio_60s=spread_recovery,
            book_update_count_10s=sum(
                candidate.event_ts > as_of - timedelta(seconds=10) for candidate in books[: index + 1]
            ),
            realized_mid_volatility_60s=pstdev(mid_returns) if len(mid_returns) > 1 else 0.0,
            bid_refill_proxy=bid_refill,
            ask_refill_proxy=ask_refill,
            mid_return_60s=mid_return_60s,
            flow_price_state=flow_price_state,
            liquidity_stress=liquidity_stress,
            flow_10s=flow_10s,
            flow_30s=flow_30s,
            flow_60s=flow_60s,
            flow_300s=flow_300s,
            smart_money_score=score,
            confidence=confidence,
            complete=complete,
            complete_60s=complete_60s,
            complete_300s=complete_300s,
            session_start=session.session_start if session else None,
            replayed=session.replayed if session else False,
            trade_eligible=bool(
                confidence >= 0.8
                and abs(score) >= 0.20
                and flow_price_state is FlowPriceState.CONFIRMED
                and liquidity_stress < 1.0
            ),
        )

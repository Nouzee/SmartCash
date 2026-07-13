from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite
from statistics import fmean, stdev
from typing import Sequence


@dataclass(frozen=True, slots=True)
class MicrostructureObservation:
    event_ts: datetime
    mid_price: float
    spread_bps: float
    depth_l1: float
    signed_flow_ratio: float
    smart_money_score: float

    def __post_init__(self) -> None:
        if self.event_ts.tzinfo is None:
            raise ValueError("event_ts must be timezone-aware")
        if not isfinite(self.mid_price) or self.mid_price <= 0:
            raise ValueError("mid_price must be finite and positive")


@dataclass(frozen=True, slots=True)
class ShockEvent:
    detected_at: datetime
    direction: int
    shock_return: float
    prior_volatility: float
    pre_spread_bps: float
    pre_depth_l1: float
    detection_spread_bps: float
    detection_depth_l1: float
    signed_flow_ratio: float
    smart_money_score: float


class ShockCategory(StrEnum):
    PERSISTENT = "persistent"
    DAMPENED = "dampened"
    REVERSED = "reversed"


@dataclass(frozen=True, slots=True)
class ShockOutcome:
    category: ShockCategory
    labelled_at: datetime
    post_return: float
    trend_ratio: float
    spread_widened: bool
    depth_depleted: bool
    sustainable_price_discovery: bool


class ShockDetector:
    """Detect a project-defined price shock using only observations through as_of."""

    def __init__(self, *, k: float = 3.0, min_history: int = 20, min_return_bps: float = 5.0) -> None:
        if k <= 0 or min_history < 2 or min_return_bps < 0:
            raise ValueError("k must be positive and min_history at least two")
        self.k = k
        self.min_history = min_history
        self.min_return_bps = min_return_bps

    def detect(
        self,
        observations: Sequence[MicrostructureObservation],
        *,
        as_of: datetime,
    ) -> ShockEvent | None:
        causal = sorted((item for item in observations if item.event_ts <= as_of), key=lambda item: item.event_ts)
        if len(causal) < self.min_history + 2:
            return None
        returns = [current.mid_price / previous.mid_price - 1 for previous, current in zip(causal, causal[1:], strict=False)]
        shock_return = returns[-1]
        prior_returns = returns[-(self.min_history + 1) : -1]
        if len(prior_returns) < self.min_history:
            return None
        volatility = stdev(prior_returns)
        threshold = max(self.k * volatility, self.min_return_bps / 10_000)
        if volatility <= 0 or abs(shock_return) <= threshold:
            return None
        prior = causal[-(self.min_history + 1) : -1]
        current = causal[-1]
        return ShockEvent(
            detected_at=current.event_ts,
            direction=1 if shock_return > 0 else -1,
            shock_return=shock_return,
            prior_volatility=volatility,
            pre_spread_bps=fmean(item.spread_bps for item in prior),
            pre_depth_l1=fmean(item.depth_l1 for item in prior),
            detection_spread_bps=current.spread_bps,
            detection_depth_l1=current.depth_l1,
            signed_flow_ratio=current.signed_flow_ratio,
            smart_money_score=current.smart_money_score,
        )


class ShockLabeler:
    """Ex-post outcome labeler; never call from the realtime feature path."""

    def __init__(self, *, horizon_seconds: int = 60, dampening_ratio: float = 0.5) -> None:
        if horizon_seconds <= 0 or not 0 < dampening_ratio <= 1:
            raise ValueError("invalid shock label parameters")
        self.horizon_seconds = horizon_seconds
        self.dampening_ratio = dampening_ratio

    def label(self, event: ShockEvent, observations: Sequence[MicrostructureObservation]) -> ShockOutcome:
        target = event.detected_at + timedelta(seconds=self.horizon_seconds)
        ordered = sorted(observations, key=lambda item: item.event_ts)
        detection = next((item for item in ordered if item.event_ts == event.detected_at), None)
        future = next((item for item in ordered if item.event_ts >= target), None)
        if detection is None or future is None:
            raise ValueError("future window is not complete")
        post_return = future.mid_price / detection.mid_price - 1
        aligned = event.direction * post_return
        trend_ratio = abs(post_return) / abs(event.shock_return) if event.shock_return else 0.0
        if aligned <= 0:
            category = ShockCategory.REVERSED
        elif trend_ratio >= self.dampening_ratio:
            category = ShockCategory.PERSISTENT
        else:
            category = ShockCategory.DAMPENED
        spread_widened = future.spread_bps > event.pre_spread_bps
        depth_depleted = future.depth_l1 < event.pre_depth_l1
        return ShockOutcome(
            category=category,
            labelled_at=future.event_ts,
            post_return=post_return,
            trend_ratio=trend_ratio,
            spread_widened=spread_widened,
            depth_depleted=depth_depleted,
            sustainable_price_discovery=bool(
                category is ShockCategory.PERSISTENT and spread_widened and depth_depleted
            ),
        )

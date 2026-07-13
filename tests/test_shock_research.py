from datetime import datetime, timedelta

import pytest

from smart_money.shocks import (
    MicrostructureObservation,
    ShockCategory,
    ShockDetector,
    ShockLabeler,
)


BASE = datetime.fromisoformat("2026-01-05T10:00:00+08:00")


def observation(seconds: int, mid: float, spread: float = 5.0, depth: float = 1_000.0) -> MicrostructureObservation:
    return MicrostructureObservation(
        event_ts=BASE + timedelta(seconds=seconds),
        mid_price=mid,
        spread_bps=spread,
        depth_l1=depth,
        signed_flow_ratio=0.5,
        smart_money_score=0.4,
    )


def test_shock_detection_is_ex_ante_and_outcome_is_labelled_later() -> None:
    pre_and_shock = [
        observation(0, 100.00),
        observation(1, 100.01),
        observation(2, 99.99),
        observation(3, 100.00),
        observation(4, 101.00),
    ]
    detector = ShockDetector(k=3.0, min_history=3)

    event = detector.detect(pre_and_shock, as_of=BASE + timedelta(seconds=4))

    assert event is not None
    assert event.detected_at == BASE + timedelta(seconds=4)
    assert event.direction == 1
    assert event.shock_return == pytest.approx(0.01)

    future = observation(64, 101.60, spread=8.0, depth=600.0)
    unchanged = detector.detect(pre_and_shock + [future], as_of=BASE + timedelta(seconds=4))
    assert unchanged == event

    outcome = ShockLabeler(horizon_seconds=60).label(event, pre_and_shock + [future])
    assert outcome.category is ShockCategory.PERSISTENT
    assert outcome.post_return == pytest.approx(101.60 / 101.00 - 1)
    assert outcome.trend_ratio > 0.5
    assert outcome.spread_widened
    assert outcome.depth_depleted
    assert outcome.sustainable_price_discovery


def test_unfinished_future_window_cannot_be_labelled() -> None:
    observations = [
        observation(0, 100.0),
        observation(1, 100.01),
        observation(2, 99.99),
        observation(3, 100.0),
        observation(4, 101.0),
    ]
    event = ShockDetector(k=3.0, min_history=3).detect(observations, as_of=BASE + timedelta(seconds=4))
    assert event is not None

    with pytest.raises(ValueError, match="future window"):
        ShockLabeler(horizon_seconds=60).label(event, observations)


def test_opposite_post_shock_move_is_reversal() -> None:
    observations = [
        observation(0, 100.0), observation(1, 100.01), observation(2, 99.99), observation(3, 100.0), observation(4, 101.0)
    ]
    event = ShockDetector(k=3.0, min_history=3).detect(observations, as_of=BASE + timedelta(seconds=4))
    assert event is not None
    outcome = ShockLabeler(horizon_seconds=60).label(event, observations + [observation(64, 100.4)])
    assert outcome.category is ShockCategory.REVERSED
    assert not outcome.sustainable_price_discovery

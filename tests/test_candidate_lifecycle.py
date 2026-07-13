from datetime import datetime, timedelta

import pytest

from smartcash.candidates import CandidateStatus, CandidateTracker
from smartcash.contracts import SourceWatermark


BASE = datetime.fromisoformat("2026-01-05T10:00:00+08:00")


def watermark(seconds: int, trade_id: str) -> SourceWatermark:
    observed_at = BASE + timedelta(seconds=seconds)
    return SourceWatermark(
        book_event_ts=observed_at,
        book_captured_at=observed_at,
        trade_event_ts=observed_at,
        trade_captured_at=observed_at,
        trade_id=trade_id,
    )


def test_candidate_requires_two_fresh_consecutive_gate_passes() -> None:
    tracker = CandidateTracker(confirmation_passes=2, observation_seconds=5)
    candidate = tracker.detect(
        symbol="00700.HK",
        direction=1,
        detected_at=BASE,
        source_watermark=watermark(0, "t0"),
    )

    first = tracker.observe(
        candidate.candidate_id,
        checkpoint_at=BASE + timedelta(seconds=1),
        gate_passed=True,
        aligned_directional_trade=True,
        source_watermark=watermark(1, "t1"),
    )
    stale = tracker.observe(
        candidate.candidate_id,
        checkpoint_at=BASE + timedelta(seconds=2),
        gate_passed=True,
        aligned_directional_trade=True,
        source_watermark=watermark(1, "t1"),
    )
    confirmed = tracker.observe(
        candidate.candidate_id,
        checkpoint_at=BASE + timedelta(seconds=3),
        gate_passed=True,
        aligned_directional_trade=True,
        source_watermark=watermark(3, "t3"),
    )
    confirmed = tracker.observe(
        candidate.candidate_id,
        checkpoint_at=BASE + timedelta(seconds=4),
        gate_passed=True,
        aligned_directional_trade=True,
        source_watermark=watermark(4, "t4"),
    )

    assert first.status is CandidateStatus.OBSERVING
    assert first.consecutive_passes == 1
    assert stale.consecutive_passes == 0
    assert confirmed.status is CandidateStatus.CONFIRMED
    assert confirmed.confirmed_at == BASE + timedelta(seconds=4)
    assert tuple(item.checkpoint_at for item in confirmed.checkpoints) == (
        BASE + timedelta(seconds=1),
        BASE + timedelta(seconds=2),
        BASE + timedelta(seconds=3),
        BASE + timedelta(seconds=4),
    )
    assert confirmed.checkpoints[-2].source_watermark.trade_id == "t3"
    assert confirmed.checkpoints[-1].source_watermark.trade_id == "t4"


def test_candidate_rejects_subsecond_confirmation_checkpoints() -> None:
    tracker = CandidateTracker(confirmation_passes=2, observation_seconds=5)
    candidate = tracker.detect(
        symbol="00700.HK",
        direction=1,
        detected_at=BASE,
        source_watermark=watermark(0, "t0"),
    )

    with pytest.raises(ValueError, match="one-second cadence"):
        tracker.observe(
            candidate.candidate_id,
            checkpoint_at=BASE + timedelta(milliseconds=500),
            gate_passed=True,
            aligned_directional_trade=True,
            source_watermark=watermark(1, "t1"),
        )


def test_expired_cluster_must_rearm_before_a_new_candidate() -> None:
    tracker = CandidateTracker(confirmation_passes=2, observation_seconds=5)
    candidate = tracker.detect(
        symbol="00700.HK",
        direction=1,
        detected_at=BASE,
        source_watermark=watermark(0, "t0"),
    )
    expired = tracker.observe(
        candidate.candidate_id,
        checkpoint_at=BASE + timedelta(seconds=6),
        gate_passed=False,
        aligned_directional_trade=False,
        source_watermark=watermark(6, "t6"),
    )

    assert expired.status is CandidateStatus.EXPIRED
    with pytest.raises(ValueError, match="not re-armed"):
        tracker.detect(
            symbol="00700.HK",
            direction=1,
            detected_at=BASE + timedelta(seconds=6),
            source_watermark=watermark(6, "t6"),
        )

    assert not tracker.observe_rearm(
        "00700.HK",
        checkpoint_at=BASE + timedelta(seconds=7),
        abnormal=False,
        source_watermark=watermark(7, "t7"),
    )
    assert tracker.observe_rearm(
        "00700.HK",
        checkpoint_at=BASE + timedelta(seconds=8),
        abnormal=False,
        source_watermark=watermark(8, "t8"),
    )

    next_candidate = tracker.detect(
        symbol="00700.HK",
        direction=-1,
        detected_at=BASE + timedelta(seconds=9),
        source_watermark=watermark(9, "t9"),
    )
    assert next_candidate.direction == -1

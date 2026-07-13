from datetime import datetime

import pytest

from smart_money.contracts import BookLevel, BookSnapshotEvent
from smart_money.engine import SmartMoneyEngine


def book(ts: str, *, bid_size: int, ask_size: int) -> BookSnapshotEvent:
    return BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=datetime.fromisoformat(ts),
        bids=(BookLevel(100.0, bid_size), BookLevel(99.9, 40)),
        asks=(BookLevel(100.1, ask_size), BookLevel(100.2, 80)),
        source="xtquant.l2thousand",
    )


def test_snapshot_exposes_causal_book_pressure_and_ofi() -> None:
    engine = SmartMoneyEngine()
    engine.ingest(book("2026-01-05T09:30:00+08:00", bid_size=60, ask_size=20))
    engine.ingest(book("2026-01-05T09:30:01+08:00", bid_size=80, ask_size=10))

    feature = engine.snapshot("00700.HK", datetime.fromisoformat("2026-01-05T09:30:01+08:00"))

    assert feature.mid_price == pytest.approx(100.05)
    assert feature.spread_bps == pytest.approx((0.1 / 100.05) * 10_000)
    assert feature.book_imbalance_l1 == pytest.approx((80 - 10) / 90)
    assert feature.book_imbalance_l2 == pytest.approx((120 - 90) / 210)
    assert feature.microprice == pytest.approx((100.1 * 80 + 100.0 * 10) / 90)
    assert feature.microprice_edge_bps == pytest.approx((feature.microprice / 100.05 - 1) * 10_000)
    assert feature.ofi_l1 == pytest.approx(30.0)
    assert feature.ofi_l1_normalized == pytest.approx(30 / 85)
    assert feature.as_of == datetime.fromisoformat("2026-01-05T09:30:01+08:00")


def test_broker_queue_cannot_be_constructed_as_l2_order_book() -> None:
    with pytest.raises(ValueError, match="l2thousand"):
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            bids=(BookLevel(100.0, 10),),
            asks=(BookLevel(100.1, 10),),
            source="xtquant.hkbrokerqueueex",
        )


def test_liquidity_recovery_uses_only_prior_l2_snapshots() -> None:
    engine = SmartMoneyEngine()
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            bids=(BookLevel(100.0, 100),),
            asks=(BookLevel(100.2, 100),),
            source="xtquant.l2thousand",
        )
    )
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=datetime.fromisoformat("2026-01-05T09:30:01+08:00"),
                bids=(BookLevel(99.8, 50),),
            asks=(BookLevel(100.3, 50),),
            source="xtquant.l2thousand",
        )
    )
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=datetime.fromisoformat("2026-01-05T09:30:02+08:00"),
            bids=(BookLevel(100.0, 90),),
            asks=(BookLevel(100.2, 90),),
            source="xtquant.l2thousand",
        )
    )

    feature = engine.snapshot("00700.HK", datetime.fromisoformat("2026-01-05T09:30:02+08:00"))

    assert feature.depth_l1 == 180
    assert feature.depth_recovery_ratio_60s == pytest.approx(0.8)
    assert feature.spread_recovery_ratio_60s == pytest.approx(1.0)
    assert feature.book_update_count_10s == 3
    # A size increase across a repricing is recovery, not a defensible refill event.
    assert feature.bid_refill_proxy == 0
    assert feature.ask_refill_proxy == 0
    assert feature.realized_mid_volatility_60s > 0

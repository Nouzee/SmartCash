from datetime import date, datetime, timedelta

import pytest

from smart_money.contracts import (
    AggressorSide,
    BookLevel,
    BookSnapshotEvent,
    SessionContext,
    TradeEvent,
)
from smart_money.engine import SmartMoneyEngine
from smart_money.identity import IdentityRecord, IdentityRegistry


BASE = datetime.fromisoformat("2026-01-05T10:00:00+08:00")


def trade(seconds: int, turnover: float, side: AggressorSide, broker: str) -> TradeEvent:
    return TradeEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=seconds),
        price=100.0,
        volume=int(turnover / 100),
        turnover=turnover,
        aggressor_side=side,
        active_broker_code=broker,
        passive_broker_code="9999",
        trade_id=str(seconds),
        side_contract="test_canonical",
    )


def registry() -> IdentityRegistry:
    return IdentityRegistry(
        (
            IdentityRecord(
                broker_code="0101",
                broker_full_name="Institutional Alpha Securities Limited",
                broker_display_name="Alpha Inst",
                participant_id="P001",
                participant_full_name="Institutional Alpha Securities Limited",
                participant_display_name="Alpha Inst",
                skill_score=0.8,
                effective_from=date(2020, 1, 1),
            ),
            IdentityRecord(
                broker_code="0102",
                broker_full_name="Other Securities Limited",
                broker_display_name="Other",
                participant_id="P002",
                participant_full_name="Other Securities Limited",
                participant_display_name="Other",
                skill_score=0.0,
                effective_from=date(2020, 1, 1),
            ),
        )
    )


def test_rolling_flow_uses_active_identity_and_excludes_neutral_direction() -> None:
    engine = SmartMoneyEngine(identity_registry=registry())
    engine.set_session(
        SessionContext(
            trade_date=BASE.date(),
            expected_open=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            session_start=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            replayed=False,
        )
    )
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=BASE,
            bids=(BookLevel(100.0, 100),),
            asks=(BookLevel(100.1, 100),),
            source="xtquant.l2thousand",
        )
    )
    engine.ingest(trade(1, 60_000, AggressorSide.BUY, "0101"))
    engine.ingest(trade(2, 20_000, AggressorSide.SELL, "0102"))
    engine.ingest(trade(3, 20_000, AggressorSide.NEUTRAL, ""))

    feature = engine.snapshot("00700.HK", BASE + timedelta(seconds=5))
    flow = feature.flow_60s

    assert flow.buy_turnover == 60_000
    assert flow.sell_turnover == 20_000
    assert flow.neutral_turnover == 20_000
    assert flow.directional_flow_ratio == pytest.approx(0.75)
    assert flow.signed_flow_ratio == pytest.approx(0.5)
    assert flow.neutral_share == pytest.approx(0.2)
    assert flow.broker_mapping_coverage == pytest.approx(1.0)
    assert flow.participant_mapping_coverage == pytest.approx(1.0)
    assert flow.skill_weighted_flow == pytest.approx(0.6)
    assert flow.top_broker_net_concentration == pytest.approx(0.75)
    assert flow.top_participant_net_concentration == pytest.approx(0.75)
    assert flow.top_brokers[0].broker_full_name == "Institutional Alpha Securities Limited"
    assert flow.top_brokers[0].broker_display_name == "Alpha Inst"
    assert feature.complete
    assert feature.confidence > 0


def test_late_live_session_cannot_be_trade_eligible() -> None:
    engine = SmartMoneyEngine(identity_registry=registry())
    engine.set_session(
        SessionContext(
            trade_date=BASE.date(),
            expected_open=datetime.fromisoformat("2026-01-05T09:30:00+08:00"),
            session_start=BASE,
            replayed=False,
        )
    )
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=BASE,
            bids=(BookLevel(100.0, 300),),
            asks=(BookLevel(100.1, 50),),
            source="xtquant.l2thousand",
        )
    )
    engine.ingest(trade(1, 100_000, AggressorSide.BUY, "0101"))

    feature = engine.snapshot("00700.HK", BASE + timedelta(seconds=2))

    assert not feature.complete
    assert feature.confidence == 0
    assert not feature.trade_eligible

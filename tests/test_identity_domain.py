from datetime import date, datetime, timedelta

import pytest

from smartcash.contracts import AggressorSide, BookLevel, BookSnapshotEvent, TradeEvent
from smartcash.engine import SmartCashEngine
from smartcash.identity import ExternalIdentityAlias, IdentityRecord, IdentityRegistry


def test_ccass_identifier_is_an_external_alias_not_a_canonical_key() -> None:
    record = IdentityRecord(
        seat_code="0101",
        seat_full_name="Seat 0101",
        seat_display_name="0101",
        broker_entity_id="broker-alpha",
        broker_entity_full_name="Alpha Securities Limited",
        broker_entity_display_name="Alpha",
        external_aliases=(
            ExternalIdentityAlias(
                source="ccass_reference",
                alias_type="participant_id",
                value="P001",
            ),
        ),
        skill_score=0.8,
        effective_from=date(2020, 1, 1),
    )
    registry = IdentityRegistry((record,))

    resolved = registry.resolve_seat("0101", date(2026, 1, 5))

    assert resolved == record
    assert resolved.broker_entity_id == "broker-alpha"
    assert resolved.external_aliases[0].value == "P001"
    assert registry.resolve_seat("P001", date(2026, 1, 5)) is None


def test_nested_seats_do_not_double_count_one_broker_entity() -> None:
    base = datetime.fromisoformat("2026-01-05T10:00:00+08:00")
    records = tuple(
        IdentityRecord(
            seat_code=seat_code,
            seat_full_name=f"Seat {seat_code}",
            seat_display_name=seat_code,
            broker_entity_id="broker-alpha",
            broker_entity_full_name="Alpha Securities Limited",
            broker_entity_display_name="Alpha",
            external_aliases=(),
            skill_score=0.5,
            effective_from=date(2020, 1, 1),
        )
        for seat_code in ("0101", "0102")
    )
    engine = SmartCashEngine(identity_registry=IdentityRegistry(records))
    engine.ingest(
        BookSnapshotEvent(
            symbol="00700.HK",
            event_ts=base,
            bids=(BookLevel(100.0, 1_000),),
            asks=(BookLevel(100.1, 1_000),),
            source="xtquant.l2thousand",
        )
    )
    for offset, seat_code in enumerate(("0101", "0102"), start=1):
        engine.ingest(
            TradeEvent(
                symbol="00700.HK",
                event_ts=base + timedelta(seconds=offset),
                price=100.1,
                volume=500,
                turnover=50_000.0,
                aggressor_side=AggressorSide.BUY,
                active_seat_code=seat_code,
                passive_seat_code="9999",
                trade_id=str(offset),
                side_contract="verified",
            )
        )

    flow = engine.snapshot("00700.HK", base + timedelta(seconds=3)).flow_10s

    assert flow.seat_identity_coverage == pytest.approx(1.0)
    assert flow.broker_entity_mapping_coverage == pytest.approx(1.0)
    assert flow.top_seat_net_concentration == pytest.approx(0.5)
    assert flow.top_broker_entity_net_concentration == pytest.approx(1.0)
    assert flow.skill_weighted_flow == pytest.approx(0.5)

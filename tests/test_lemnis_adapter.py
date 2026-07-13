from datetime import datetime, timedelta

from smartcash.execution import OrderSide, ProtectedIocOrder
from smartcash.integrations.lemnis import (
    LEMNIS_ORDER_ADAPTER_SCHEMA_VERSION,
    LemnisPublicAdapter,
)


BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def test_lemnis_adapter_emits_a_versioned_public_order_batch_payload() -> None:
    order = ProtectedIocOrder(
        order_id="candidate-1-entry",
        symbol="00700.HK",
        side=OrderSide.BUY,
        quantity=500,
        decision_midpoint=100.0,
        decision_time=BASE,
        eligible_from=BASE + timedelta(milliseconds=100),
        expires_at=BASE + timedelta(seconds=5),
    )

    payload = LemnisPublicAdapter().to_order_batch_payload(order)

    assert payload.schema_version == LEMNIS_ORDER_ADAPTER_SCHEMA_VERSION
    assert payload.intent_id == order.order_id
    assert payload.batch_kind == "smartcash_protected_ioc"
    assert payload.eligible_from == order.eligible_from
    assert payload.expire_at == order.expires_at
    assert payload.orders[0].security == "00700.HK"
    assert payload.orders[0].side == "BUY"
    assert payload.orders[0].quantity == 500
    assert payload.smartcash_execution_owner is True
    assert payload.to_dict()["orders"][0]["side"] == "BUY"


def test_lemnis_adapter_preserves_exit_sell_side_without_creating_a_short_policy() -> None:
    order = ProtectedIocOrder(
        order_id="candidate-1-exit",
        symbol="00700.HK",
        side=OrderSide.SELL,
        quantity=500,
        decision_midpoint=100.0,
        decision_time=BASE,
        eligible_from=BASE + timedelta(seconds=1),
        expires_at=BASE + timedelta(seconds=5),
    )

    payload = LemnisPublicAdapter().to_order_batch_payload(order)

    assert payload.orders[0].side == "SELL"
    assert "directional_taker_only" in payload.reason

from datetime import datetime

from smartcash.contracts import AggressorSide
from smartcash.xtquant import DirectionConvention, normalize_hktransaction


def test_vendor_direction_and_active_identity_are_explicit() -> None:
    sell = normalize_hktransaction(
        symbol="00700.HK",
        raw={
            "time": 1_767_576_601_000,
            "price": 400.0,
            "volume": 1_000,
            "dir": 1,
            "brokerNo": 9999,
            "activeBrokerNo": 101,
            "tradeID": 7,
        },
        convention=DirectionConvention.VENDOR_DOC,
    )
    buy = normalize_hktransaction(
        symbol="00700.HK",
        raw={"time": 1_767_576_602_000, "price": 400.2, "volume": 500, "dir": 2, "brokerNo": 8888, "activeBrokerNo": 102},
        convention=DirectionConvention.VENDOR_DOC,
    )

    assert sell.event_ts == datetime.fromisoformat("2026-01-05T09:30:01+08:00")
    assert sell.aggressor_side is AggressorSide.SELL
    assert buy.aggressor_side is AggressorSide.BUY
    assert sell.active_broker_code == "0101"
    assert sell.passive_broker_code == "9999"
    assert sell.turnover == 400_000.0
    assert sell.side_contract == "xtquant_vendor_doc_dir_1_sell_2_buy"


def test_missing_active_broker_never_falls_back_to_passive_broker() -> None:
    trade = normalize_hktransaction(
        symbol="00700.HK",
        raw={"time": 1_767_576_601_000, "price": 400.0, "volume": 100, "dir": 2, "brokerNo": 101},
        convention=DirectionConvention.VENDOR_DOC,
    )

    assert trade.active_broker_code == ""
    assert trade.passive_broker_code == "0101"

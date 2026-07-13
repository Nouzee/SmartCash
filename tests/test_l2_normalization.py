from datetime import datetime

from smart_money.xtquant import normalize_l2thousand


def test_l2thousand_arrays_become_valid_full_snapshot() -> None:
    book = normalize_l2thousand(
        symbol="00700.HK",
        raw={
            "time": 1_767_576_601_000,
            "bidPrice": [400.0, 399.8, 0.0],
            "bidVolume": [10_000, 20_000, 0],
            "askPrice": [400.2, 400.4, 0.0],
            "askVolume": [8_000, 15_000, 0],
        },
    )

    assert book.event_ts == datetime.fromisoformat("2026-01-05T09:30:01+08:00")
    assert [(level.price, level.size) for level in book.bids] == [(400.0, 10_000), (399.8, 20_000)]
    assert [(level.price, level.size) for level in book.asks] == [(400.2, 8_000), (400.4, 15_000)]
    assert book.source == "xtquant.l2thousand"

import json

import pytest

from smart_money.cli import load_events
from smart_money.xtquant import DirectionConvention


def write_jsonl(path, rows) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def trade(seq: int, timestamp_ms: int, trade_id: str) -> dict[str, object]:
    return {
        "kind": "hktransaction",
        "symbol": "00700.HK",
        "payload": {
            "time": timestamp_ms,
            "price": 400.0,
            "volume": 100,
            "dir": 2,
            "activeBrokerNo": 101,
            "brokerNo": 9999,
            "tradeID": trade_id,
            "seq": seq,
        },
    }


def test_tape_audit_detects_file_order_duplicates_and_sequence_gaps(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    write_jsonl(
        path,
        [
            trade(2, 1_767_576_602_000, "duplicate"),
            trade(4, 1_767_576_601_000, "duplicate"),
        ],
    )

    events, audit = load_events(path, DirectionConvention.VENDOR_DOC)

    assert [event.event_ts for event in events] == sorted(event.event_ts for event in events)
    assert audit.out_of_order_count == 1
    assert audit.duplicate_trade_id_count == 1
    assert audit.sequence_gap_count == 1
    assert not audit.tape_complete


def test_generic_tick_alias_is_rejected_instead_of_relabelled_as_xtquant(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    row = trade(1, 1_767_576_601_000, "1")
    row["kind"] = "tick"
    write_jsonl(path, [row])

    with pytest.raises(ValueError, match="unsupported event kind"):
        load_events(path, DirectionConvention.VENDOR_DOC)

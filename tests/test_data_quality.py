from datetime import date, datetime, timedelta

import pytest

from smartcash.contracts import AggressorSide, BookLevel, BookSnapshotEvent, TradeEvent
from smartcash.data_quality import (
    BookInputAuditor,
    SymbolTradeCaptureAudit,
    TapeAuditor,
    TradeCaptureAudit,
    build_data_quality_rows,
    expected_hk_active_session_seconds,
)
from smartcash.identity import IdentityRecord, IdentityRegistry


BASE = datetime.fromisoformat("2026-01-05T09:30:00+08:00")


def trade(milliseconds: int, turnover: float, broker: str, trade_id: str) -> TradeEvent:
    return TradeEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(milliseconds=milliseconds),
        price=100.0,
        volume=int(turnover / 100),
        turnover=turnover,
        aggressor_side=AggressorSide.BUY,
        active_seat_code=broker,
        passive_seat_code="9999",
        trade_id=trade_id,
        side_contract="test",
    )


def book(seconds: int) -> BookSnapshotEvent:
    return BookSnapshotEvent(
        symbol="00700.HK",
        event_ts=BASE + timedelta(seconds=seconds),
        bids=(BookLevel(100.0, 100),),
        asks=(BookLevel(100.1, 100),),
        source="xtquant.l2thousand",
    )


def audited_books(*books: BookSnapshotEvent):
    auditor = BookInputAuditor()
    for item in books:
        auditor.record_valid(item, captured_at=item.event_ts)
    return auditor.snapshot()


def full_session_books() -> tuple[BookSnapshotEvent, ...]:
    morning = range(0, 9_001, 5)
    afternoon = range(12_600, 23_401, 5)
    return tuple(book(seconds) for seconds in (*morning, *afternoon))


def complete_trade_capture() -> TradeCaptureAudit:
    return TradeCaptureAudit(
        (
            SymbolTradeCaptureAudit(
                symbol="00700.HK",
                source="xtquant.hktransaction",
                subscription_acknowledged=True,
                subscribed_at=BASE - timedelta(seconds=1),
                first_heartbeat_at=BASE,
                last_heartbeat_at=BASE.replace(hour=16, minute=0),
                heartbeat_count=332,
                max_heartbeat_gap_seconds=60.0,
                dropped_callback_count=0,
                expected_open=BASE,
                expected_end=BASE.replace(hour=16, minute=0),
            ),
        )
    )


def test_phase_zero_report_combines_tape_book_and_identity_coverage() -> None:
    mapped = trade(200, 300_000, "0101", "t1")
    unmapped = trade(300, 100_000, "9998", "t2")
    auditor = TapeAuditor()
    auditor.record(mapped, raw_sequence=1, captured_at=mapped.event_ts)
    auditor.record(unmapped, raw_sequence=2, captured_at=unmapped.event_ts)
    registry = IdentityRegistry(
        (
            IdentityRecord(
                "0101",
                "Seat 0101",
                "0101",
                "broker-alpha",
                "Alpha Securities Limited",
                "Alpha",
                (),
                0.5,
                date(2020, 1, 1),
            ),
        )
    )

    books = full_session_books()
    rows = build_data_quality_rows(
        [*books, mapped, unmapped],
        tape_audit=auditor.snapshot(),
        trade_capture_audit=complete_trade_capture(),
        book_input_audit=audited_books(*books),
        expected_open=BASE,
        expected_end=BASE + timedelta(seconds=23_400),
        expected_symbols=("00700.HK",),
        max_book_gap_seconds=5.0,
        identity_registry=registry,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "00700.HK"
    assert row.trade_count == 2
    assert row.book_count == len(books)
    assert row.tape_complete
    assert row.trade_capture_complete
    assert row.book_coverage_complete
    assert row.session_duration_complete
    assert row.combined_complete
    assert row.max_book_gap_seconds == pytest.approx(5.0)
    assert row.active_seat_disclosure_coverage == pytest.approx(1.0)
    assert row.broker_entity_mapping_coverage == pytest.approx(0.75)


def test_missing_l2_or_incomplete_sequence_blocks_combined_coverage() -> None:
    event = trade(200, 100_000, "0101", "t1")
    auditor = TapeAuditor()
    auditor.record(event, raw_sequence=None, captured_at=event.event_ts)

    row = build_data_quality_rows(
        [event],
        tape_audit=auditor.snapshot(),
        book_input_audit=BookInputAuditor().snapshot(),
        expected_open=BASE,
        expected_end=BASE + timedelta(seconds=23_400),
        expected_symbols=("00700.HK",),
        max_book_gap_seconds=2.0,
    )[0]

    assert not row.sequence_present
    assert not row.tape_complete
    assert not row.book_coverage_complete
    assert not row.combined_complete


def test_hk_session_contract_distinguishes_full_and_exchange_half_days() -> None:
    assert expected_hk_active_session_seconds(
        BASE, BASE.replace(hour=16, minute=0)
    ) == pytest.approx(19_800.0)
    half_day_open = datetime.fromisoformat("2026-02-16T09:30:00+08:00")
    assert expected_hk_active_session_seconds(
        half_day_open, half_day_open.replace(hour=12, minute=0)
    ) == pytest.approx(9_000.0)

    with pytest.raises(ValueError, match="HKEX session contract"):
        expected_hk_active_session_seconds(BASE, BASE + timedelta(seconds=1))

    for invalid_open in (
        datetime.fromisoformat("2026-01-04T09:30:00+08:00"),
        datetime.fromisoformat("2026-01-01T09:30:00+08:00"),
        datetime.fromisoformat("2026-01-05T09:30:00+07:00"),
    ):
        with pytest.raises(ValueError, match="HKEX session contract"):
            expected_hk_active_session_seconds(
                invalid_open, invalid_open.replace(hour=16, minute=0)
            )


def test_truncated_morning_capture_cannot_be_a_complete_session() -> None:
    event = trade(200, 100_000, "0101", "t1")
    auditor = TapeAuditor()
    auditor.record(event, raw_sequence=1, captured_at=event.event_ts)

    first_book, last_book = book(0), book(1)
    with pytest.raises(ValueError, match="HKEX session contract"):
        build_data_quality_rows(
            [first_book, event, last_book],
            tape_audit=auditor.snapshot(),
            book_input_audit=audited_books(first_book, last_book),
            expected_open=BASE,
            expected_end=BASE + timedelta(seconds=1),
            expected_symbols=("00700.HK",),
            max_book_gap_seconds=2.0,
        )


def test_missing_expected_symbol_gets_an_explicit_failed_row() -> None:
    event = trade(200, 100_000, "0101", "t1")
    auditor = TapeAuditor()
    auditor.record(event, raw_sequence=1, captured_at=event.event_ts)

    rows = build_data_quality_rows(
        [event],
        tape_audit=auditor.snapshot(),
        book_input_audit=BookInputAuditor().snapshot(),
        expected_open=BASE,
        expected_end=BASE.replace(hour=16, minute=0),
        expected_symbols=("00700.HK", "00939.HK"),
        max_book_gap_seconds=5.0,
    )

    missing = next(row for row in rows if row.symbol == "00939.HK")
    assert missing.trade_count == 0
    assert missing.book_count == 0
    assert missing.first_event_ts is None
    assert not missing.combined_complete


def test_trade_arrival_provenance_is_a_hard_tape_gate() -> None:
    first = trade(0, 100_000, "0101", "t1")
    second = trade(1, 100_000, "0101", "t2")
    auditor = TapeAuditor(max_arrival_latency_ms=1.0)
    auditor.record(first, raw_sequence=1, captured_at=first.event_ts + timedelta(milliseconds=2))
    auditor.record(second, raw_sequence=2, captured_at=second.event_ts - timedelta(milliseconds=1))

    audit = auditor.snapshot().for_symbol("00700.HK")
    assert audit is not None
    assert audit.arrival_timestamp_coverage == pytest.approx(1.0)
    assert audit.stale_trade_count == 1
    assert audit.negative_arrival_latency_count == 1
    assert audit.arrival_out_of_order_count == 1
    assert not audit.tape_complete


def test_trade_capture_envelope_is_required_beyond_fragment_sequence_integrity() -> None:
    event = trade(0, 100_000, "0101", "t1")
    tape = TapeAuditor()
    tape.record(event, raw_sequence=1, captured_at=event.event_ts)
    books = full_session_books()

    row = build_data_quality_rows(
        [event, *books],
        tape_audit=tape.snapshot(),
        trade_capture_audit=TradeCaptureAudit(()),
        book_input_audit=audited_books(*books),
        expected_open=BASE,
        expected_end=BASE.replace(hour=16, minute=0),
        expected_symbols=("00700.HK",),
        max_book_gap_seconds=5.0,
    )[0]

    assert row.tape_complete
    assert not row.trade_capture_complete
    assert not row.combined_complete


def test_book_raw_event_and_arrival_order_are_hard_input_gates() -> None:
    later = book(2)
    earlier = book(1)
    auditor = BookInputAuditor()
    auditor.record_valid(later, captured_at=later.event_ts)
    auditor.record_valid(earlier, captured_at=earlier.event_ts - timedelta(milliseconds=1))

    audit = auditor.snapshot().for_symbol("00700.HK")
    assert audit is not None
    assert audit.event_out_of_order_count == 1
    assert audit.arrival_out_of_order_count == 1
    assert audit.negative_arrival_latency_count == 1
    assert not audit.input_complete


def test_phase_zero_latency_and_book_gap_thresholds_can_only_be_tightened() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1000\]"):
        TapeAuditor(max_arrival_latency_ms=1_001.0)

    with pytest.raises(ValueError, match=r"\(0, 5\]"):
        build_data_quality_rows(
            [],
            tape_audit=TapeAuditor().snapshot(),
            book_input_audit=BookInputAuditor().snapshot(),
            expected_open=BASE,
            expected_end=BASE.replace(hour=16, minute=0),
            expected_symbols=("00700.HK",),
            max_book_gap_seconds=5.1,
        )

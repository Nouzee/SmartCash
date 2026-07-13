from datetime import date, timedelta

from smartcash.walk_forward import WalkForwardConfig, build_walk_forward_folds


def _trading_dates(count: int) -> tuple[date, ...]:
    start = date(2025, 1, 2)
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return tuple(dates)


def test_walk_forward_builds_rolling_folds_with_embargo_sessions() -> None:
    dates = _trading_dates(122)
    config = WalkForwardConfig(
        train_sessions=60,
        validation_sessions=20,
        test_sessions=20,
        embargo_sessions=1,
        step_sessions=20,
    )

    folds = build_walk_forward_folds(dates, config)

    assert len(folds) == 2
    first = folds[0]
    assert len(first.train_dates) == 60
    assert len(first.validation_dates) == 20
    assert len(first.test_dates) == 20
    assert first.train_dates[-1] < first.train_validation_embargo[0] < first.validation_dates[0]
    assert first.validation_dates[-1] < first.validation_test_embargo[0] < first.test_dates[0]
    assert folds[1].train_dates[0] == dates[20]
    assert folds[1].test_dates[-1] == dates[-1]


def test_walk_forward_rejects_unsorted_or_duplicate_dates() -> None:
    config = WalkForwardConfig()
    day = date(2025, 1, 2)

    for invalid in ((day, day), (day + timedelta(days=1), day)):
        try:
            build_walk_forward_folds(invalid, config)
        except ValueError as error:
            assert "strictly increasing" in str(error)
        else:
            raise AssertionError("invalid trading dates must be rejected")


def test_walk_forward_returns_no_fold_when_history_is_too_short() -> None:
    assert build_walk_forward_folds(_trading_dates(101), WalkForwardConfig()) == ()

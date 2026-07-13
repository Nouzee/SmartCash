"""Date-level walk-forward partitions for causal SmartCash experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    train_sessions: int = 60
    validation_sessions: int = 20
    test_sessions: int = 20
    embargo_sessions: int = 1
    step_sessions: int = 20

    def __post_init__(self) -> None:
        values = (
            self.train_sessions,
            self.validation_sessions,
            self.test_sessions,
            self.embargo_sessions,
            self.step_sessions,
        )
        if any(value <= 0 for value in values):
            raise ValueError("all walk-forward session counts must be positive")

    @property
    def required_sessions(self) -> int:
        return (
            self.train_sessions
            + self.embargo_sessions
            + self.validation_sessions
            + self.embargo_sessions
            + self.test_sessions
        )


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_index: int
    train_dates: tuple[date, ...]
    train_validation_embargo: tuple[date, ...]
    validation_dates: tuple[date, ...]
    validation_test_embargo: tuple[date, ...]
    test_dates: tuple[date, ...]


def build_walk_forward_folds(
    trading_dates: Sequence[date],
    config: WalkForwardConfig | None = None,
) -> tuple[WalkForwardFold, ...]:
    """Build fixed-width rolling folds without splitting a trading session.

    The caller supplies the point-in-time eligible trading calendar.  All
    symbols for a date therefore remain in the same partition, while embargo
    dates are explicitly retained for audit rather than silently discarded.
    """

    config = config or WalkForwardConfig()
    dates = tuple(trading_dates)
    if any(left >= right for left, right in zip(dates, dates[1:], strict=False)):
        raise ValueError("trading_dates must be strictly increasing and unique")

    folds: list[WalkForwardFold] = []
    start = 0
    while start + config.required_sessions <= len(dates):
        cursor = start
        train = dates[cursor : cursor + config.train_sessions]
        cursor += config.train_sessions
        train_embargo = dates[cursor : cursor + config.embargo_sessions]
        cursor += config.embargo_sessions
        validation = dates[cursor : cursor + config.validation_sessions]
        cursor += config.validation_sessions
        validation_embargo = dates[cursor : cursor + config.embargo_sessions]
        cursor += config.embargo_sessions
        test = dates[cursor : cursor + config.test_sessions]
        folds.append(
            WalkForwardFold(
                fold_index=len(folds),
                train_dates=train,
                train_validation_embargo=train_embargo,
                validation_dates=validation,
                validation_test_embargo=validation_embargo,
                test_dates=test,
            )
        )
        start += config.step_sessions
    return tuple(folds)

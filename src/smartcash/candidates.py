from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from .contracts import SourceWatermark


class CandidateStatus(StrEnum):
    OBSERVING = "observing"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CandidateCheckpoint:
    checkpoint_at: datetime
    gate_passed: bool
    aligned_directional_trade: bool
    fresh_book: bool
    fresh_trade: bool
    passed: bool
    source_watermark: SourceWatermark


@dataclass(frozen=True, slots=True)
class CandidateShock:
    candidate_id: str
    symbol: str
    direction: int
    detected_at: datetime
    expires_at: datetime
    status: CandidateStatus
    consecutive_passes: int
    last_checkpoint_at: datetime
    source_watermark: SourceWatermark
    checkpoints: tuple[CandidateCheckpoint, ...] = ()
    confirmed_at: datetime | None = None
    expiry_reason: str = ""


@dataclass(slots=True)
class _SymbolLifecycle:
    active_candidate_id: str | None = None
    armed: bool = True
    episode_open: bool = False
    rearm_passes: int = 0
    rearm_watermark: SourceWatermark | None = None
    rearm_checkpoint_at: datetime | None = None


class CandidateTracker:
    """Public lifecycle for one-shot, causally confirmed shock candidates."""

    def __init__(self, *, confirmation_passes: int = 2, observation_seconds: int = 5) -> None:
        if confirmation_passes <= 0 or observation_seconds <= 0:
            raise ValueError("candidate confirmation parameters must be positive")
        self.confirmation_passes = confirmation_passes
        self.observation_seconds = observation_seconds
        self._candidates: dict[str, CandidateShock] = {}
        self._symbol_lifecycle: dict[str, _SymbolLifecycle] = {}
        self._next_id = 1

    def detect(
        self,
        *,
        symbol: str,
        direction: int,
        detected_at: datetime,
        source_watermark: SourceWatermark,
    ) -> CandidateShock:
        if not symbol:
            raise ValueError("candidate symbol is required")
        if direction not in (-1, 1):
            raise ValueError("candidate direction must be -1 or 1")
        if detected_at.tzinfo is None:
            raise ValueError("detected_at must be timezone-aware")
        lifecycle = self._lifecycle(symbol)
        if lifecycle.active_candidate_id is not None:
            raise ValueError(f"symbol already has an active candidate: {symbol}")
        if not lifecycle.armed:
            raise ValueError(f"symbol is not re-armed: {symbol}")
        candidate_id = f"candidate-{self._next_id}"
        self._next_id += 1
        candidate = CandidateShock(
            candidate_id=candidate_id,
            symbol=symbol,
            direction=direction,
            detected_at=detected_at,
            expires_at=detected_at + timedelta(seconds=self.observation_seconds),
            status=CandidateStatus.OBSERVING,
            consecutive_passes=0,
            last_checkpoint_at=detected_at,
            source_watermark=source_watermark,
        )
        self._candidates[candidate_id] = candidate
        lifecycle.active_candidate_id = candidate_id
        lifecycle.armed = False
        return candidate

    def observe(
        self,
        candidate_id: str,
        *,
        checkpoint_at: datetime,
        gate_passed: bool,
        aligned_directional_trade: bool,
        source_watermark: SourceWatermark,
    ) -> CandidateShock:
        candidate = self._candidates[candidate_id]
        if candidate.status is not CandidateStatus.OBSERVING:
            raise ValueError(f"candidate is already terminal: {candidate.status.value}")
        if checkpoint_at.tzinfo is None:
            raise ValueError("checkpoint_at must be timezone-aware")
        if checkpoint_at <= candidate.last_checkpoint_at:
            raise ValueError("candidate checkpoints must be strictly increasing")
        if checkpoint_at - candidate.last_checkpoint_at < timedelta(seconds=1):
            raise ValueError("candidate checkpoints must follow one-second cadence")
        if checkpoint_at > candidate.expires_at:
            expired = replace(
                candidate,
                status=CandidateStatus.EXPIRED,
                consecutive_passes=0,
                last_checkpoint_at=checkpoint_at,
                expiry_reason="confirmation window elapsed",
            )
            self._store_terminal(expired, episode_open=False)
            return expired

        previous = candidate.source_watermark
        fresh_book = source_watermark.book_captured_at > previous.book_captured_at
        fresh_trade = bool(
            source_watermark.trade_captured_at is not None
            and (
                previous.trade_captured_at is None
                or source_watermark.trade_captured_at > previous.trade_captured_at
            )
        )
        passed = gate_passed and aligned_directional_trade and fresh_book and fresh_trade
        consecutive_cadence = checkpoint_at - candidate.last_checkpoint_at == timedelta(seconds=1)
        checkpoint = CandidateCheckpoint(
            checkpoint_at=checkpoint_at,
            gate_passed=gate_passed,
            aligned_directional_trade=aligned_directional_trade,
            fresh_book=fresh_book,
            fresh_trade=fresh_trade,
            passed=passed,
            source_watermark=source_watermark,
        )
        consecutive_passes = (
            candidate.consecutive_passes + 1
            if passed and consecutive_cadence
            else 1 if passed else 0
        )
        status = (
            CandidateStatus.CONFIRMED
            if consecutive_passes >= self.confirmation_passes
            else CandidateStatus.OBSERVING
        )
        updated = replace(
            candidate,
            status=status,
            consecutive_passes=consecutive_passes,
            last_checkpoint_at=checkpoint_at,
            source_watermark=source_watermark,
            checkpoints=candidate.checkpoints + (checkpoint,),
            confirmed_at=checkpoint_at if status is CandidateStatus.CONFIRMED else None,
        )
        if status is CandidateStatus.CONFIRMED:
            self._store_terminal(updated, episode_open=True)
        else:
            self._candidates[candidate_id] = updated
        return updated

    def observe_rearm(
        self,
        symbol: str,
        *,
        checkpoint_at: datetime,
        abnormal: bool,
        source_watermark: SourceWatermark,
    ) -> bool:
        lifecycle = self._lifecycle(symbol)
        if lifecycle.active_candidate_id is not None or lifecycle.episode_open:
            raise ValueError(f"symbol cannot re-arm while a candidate or episode is active: {symbol}")
        if lifecycle.armed:
            return True
        previous_checkpoint = lifecycle.rearm_checkpoint_at
        if previous_checkpoint is not None and checkpoint_at <= previous_checkpoint:
            raise ValueError("re-arm checkpoints must be strictly increasing")
        previous = lifecycle.rearm_watermark
        fresh = previous is None or _watermark_advanced(previous, source_watermark)
        lifecycle.rearm_passes = lifecycle.rearm_passes + 1 if fresh and not abnormal else 0
        lifecycle.rearm_watermark = source_watermark
        lifecycle.rearm_checkpoint_at = checkpoint_at
        if lifecycle.rearm_passes >= 2:
            lifecycle.armed = True
            return True
        return False

    def end_episode(
        self,
        candidate_id: str,
        *,
        ended_at: datetime,
        source_watermark: SourceWatermark,
    ) -> None:
        candidate = self._candidates[candidate_id]
        if candidate.status is not CandidateStatus.CONFIRMED:
            raise ValueError("only a confirmed candidate can own a trade episode")
        lifecycle = self._lifecycle(candidate.symbol)
        if not lifecycle.episode_open:
            raise ValueError("candidate trade episode is not open")
        lifecycle.episode_open = False
        lifecycle.rearm_passes = 0
        lifecycle.rearm_watermark = source_watermark
        lifecycle.rearm_checkpoint_at = ended_at

    def _store_terminal(self, candidate: CandidateShock, *, episode_open: bool) -> None:
        self._candidates[candidate.candidate_id] = candidate
        lifecycle = self._lifecycle(candidate.symbol)
        lifecycle.active_candidate_id = None
        lifecycle.armed = False
        lifecycle.episode_open = episode_open
        lifecycle.rearm_passes = 0
        lifecycle.rearm_watermark = candidate.source_watermark
        lifecycle.rearm_checkpoint_at = candidate.last_checkpoint_at

    def _lifecycle(self, symbol: str) -> _SymbolLifecycle:
        return self._symbol_lifecycle.setdefault(symbol, _SymbolLifecycle())


def _watermark_advanced(previous: SourceWatermark, current: SourceWatermark) -> bool:
    if current.book_captured_at > previous.book_captured_at:
        return True
    return bool(
        current.trade_captured_at is not None
        and (
            previous.trade_captured_at is None
            or current.trade_captured_at > previous.trade_captured_at
        )
    )

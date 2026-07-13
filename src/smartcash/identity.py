from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    broker_code: str
    broker_full_name: str
    broker_display_name: str
    participant_id: str
    participant_full_name: str
    participant_display_name: str
    skill_score: float
    effective_from: date
    effective_to: date | None = None

    def __post_init__(self) -> None:
        if not self.broker_code:
            raise ValueError("broker_code is required")
        if not -1 <= self.skill_score <= 1:
            raise ValueError("skill_score must be within [-1, 1]")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot precede effective_from")


class IdentityRegistry:
    """As-of broker/participant identity and lagged skill priors."""

    def __init__(self, records: tuple[IdentityRecord, ...] = ()) -> None:
        self._by_broker: dict[str, list[IdentityRecord]] = {}
        for record in records:
            self._by_broker.setdefault(record.broker_code, []).append(record)
        for values in self._by_broker.values():
            values.sort(key=lambda item: item.effective_from)

    def resolve(self, broker_code: str, as_of: date) -> IdentityRecord | None:
        matches = [
            record
            for record in self._by_broker.get(broker_code, ())
            if record.effective_from <= as_of and (record.effective_to is None or as_of <= record.effective_to)
        ]
        return matches[-1] if matches else None


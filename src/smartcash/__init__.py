"""SmartCash causal HK market-microstructure research engine."""

from .contracts import AggressorSide, BookLevel, BookSnapshotEvent, FeatureSnapshot, FlowPriceState, TradeEvent
from .engine import SmartMoneyEngine

PROJECT_NAME = "SmartCash"
SNAPSHOT_SCHEMA_VERSION = "1.0"
SmartCashEngine = SmartMoneyEngine

__all__ = [
    "AggressorSide",
    "BookLevel",
    "BookSnapshotEvent",
    "FeatureSnapshot",
    "FlowPriceState",
    "PROJECT_NAME",
    "SNAPSHOT_SCHEMA_VERSION",
    "SmartCashEngine",
    "SmartMoneyEngine",
    "TradeEvent",
]

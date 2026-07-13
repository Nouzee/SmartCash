"""SmartCash causal HK market-microstructure research engine."""

from .contracts import (
    SNAPSHOT_SCHEMA_VERSION,
    AggressorSide,
    BookLevel,
    BookSnapshotEvent,
    FeatureSnapshot,
    FlowPriceState,
    MicrostructureStepSnapshot,
    TradeEvent,
)
from .engine import SmartCashEngine, SmartMoneyEngine
from .execution import (
    ExecutionCapacity,
    IocExecutionResult,
    IocExecutionStatus,
    OrderSide,
    PointInTimeInstrumentRules,
    ProtectedIocExecutor,
    ProtectedIocOrder,
)
from .walk_forward import WalkForwardConfig, WalkForwardFold, build_walk_forward_folds

PROJECT_NAME = "SmartCash"
__all__ = [
    "AggressorSide",
    "BookLevel",
    "BookSnapshotEvent",
    "FeatureSnapshot",
    "FlowPriceState",
    "MicrostructureStepSnapshot",
    "IocExecutionResult",
    "ExecutionCapacity",
    "IocExecutionStatus",
    "OrderSide",
    "PointInTimeInstrumentRules",
    "PROJECT_NAME",
    "SNAPSHOT_SCHEMA_VERSION",
    "SmartCashEngine",
    "SmartMoneyEngine",
    "ProtectedIocExecutor",
    "ProtectedIocOrder",
    "TradeEvent",
    "WalkForwardConfig",
    "WalkForwardFold",
    "build_walk_forward_folds",
]

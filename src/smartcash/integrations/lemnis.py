"""Thin adapter to Lemnis public order schemas.

SmartCash remains the execution authority for microstructure fills.  Lemnis can
consume these batches for public order lifecycle, risk, ledger, and replay
components, but must not reconstruct or reinterpret the L2 book.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..execution import OrderSide, ProtectedIocOrder


LEMNIS_ORDER_ADAPTER_SCHEMA_VERSION = "smartcash.lemnis.order.v1"


class LemnisUnavailableError(RuntimeError):
    """Raised when optional Lemnis public schemas cannot be imported."""


@dataclass(frozen=True, slots=True)
class LemnisOrderPayload:
    security: str
    side: str
    quantity: int

    def to_dict(self) -> dict[str, object]:
        return {
            "security": self.security,
            "side": self.side,
            "quantity": self.quantity,
        }


@dataclass(frozen=True, slots=True)
class LemnisOrderBatchPayload:
    schema_version: str
    intent_id: str
    batch_kind: str
    reason: str
    eligible_from: datetime
    expire_at: datetime
    cancel_order_ids: tuple[str, ...]
    orders: tuple[LemnisOrderPayload, ...]
    smartcash_execution_owner: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "intent_id": self.intent_id,
            "batch_kind": self.batch_kind,
            "reason": self.reason,
            "eligible_from": self.eligible_from.isoformat(),
            "expire_at": self.expire_at.isoformat(),
            "cancel_order_ids": list(self.cancel_order_ids),
            "orders": [order.to_dict() for order in self.orders],
            "smartcash_execution_owner": self.smartcash_execution_owner,
        }


class LemnisPublicAdapter:
    """Convert SmartCash IOC intents through a versioned, auditable seam."""

    def to_order_batch_payload(self, order: ProtectedIocOrder) -> LemnisOrderBatchPayload:
        side = "BUY" if order.side is OrderSide.BUY else "SELL"
        return LemnisOrderBatchPayload(
            schema_version=LEMNIS_ORDER_ADAPTER_SCHEMA_VERSION,
            intent_id=order.order_id,
            batch_kind="smartcash_protected_ioc",
            reason="smartcash_directional_taker_only",
            eligible_from=order.eligible_from,
            expire_at=order.expires_at,
            cancel_order_ids=(),
            orders=(
                LemnisOrderPayload(
                    security=order.symbol,
                    side=side,
                    quantity=order.quantity,
                ),
            ),
            smartcash_execution_owner=True,
        )

    def materialize_public_order_batch(self, payload: LemnisOrderBatchPayload) -> Any:
        """Materialize Lemnis public dataclasses when the optional package exists.

        The returned batch carries intent/lifecycle data only.  SmartCash's
        ``ProtectedIocExecutor`` remains responsible for book consumption and
        prices because current Lemnis public contexts are daily/minute based.
        """

        if not payload.smartcash_execution_owner:
            raise ValueError("SmartCash must remain the microstructure execution owner")
        try:
            from lemnis.schema import ExecutableOrder, ExecutableOrderBatch
            from lemnis.schema import OrderSide as LemnisOrderSide
        except (ImportError, ModuleNotFoundError) as error:
            raise LemnisUnavailableError(
                "Lemnis public schemas are unavailable; install Lemnis and its declared dependencies"
            ) from error

        orders = tuple(
            ExecutableOrder(
                security=order.security,
                side=LemnisOrderSide(order.side),
                quantity=order.quantity,
            )
            for order in payload.orders
        )
        return ExecutableOrderBatch(
            intent_id=payload.intent_id,
            batch_kind=payload.batch_kind,
            reason=payload.reason,
            eligible_from=payload.eligible_from,
            expire_at=payload.expire_at,
            cancel_order_ids=payload.cancel_order_ids,
            orders=orders,
        )

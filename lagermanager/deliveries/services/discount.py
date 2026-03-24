"""Skonto (cash discount) application service."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deliveries.models import Delivery


def apply_skonto(delivery: Delivery, percent: float) -> None:
    """
    Apply a percentage discount to all detail line prices of a delivery.
    Modifies unit_price in place (saves each detail).
    """
    factor = Decimal(str(1 - percent / 100))
    for detail in delivery.details.all():
        detail.unit_price = (detail.unit_price * factor).quantize(Decimal('0.0001'))
        detail.save(update_fields=['unit_price'])

"""Skonto (cash discount) application service."""
from decimal import Decimal


def apply_skonto(delivery, percent: float) -> None:
    """
    Apply a percentage discount to all detail line prices of a delivery.
    Modifies unit_price in place (saves each detail).
    """
    factor = Decimal(str(1 - percent / 100))
    for detail in delivery.details.all():
        detail.unit_price = (detail.unit_price * factor).quantize(Decimal('0.0001'))
        detail.save(update_fields=['unit_price'])

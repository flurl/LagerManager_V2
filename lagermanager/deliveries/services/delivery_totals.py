"""Delivery net/gross total calculations."""
from decimal import Decimal


def compute_detail_net(quantity: Decimal, unit_price: Decimal) -> Decimal:
    return quantity * unit_price


def compute_detail_gross(quantity: Decimal, unit_price: Decimal, tax_percent: Decimal) -> Decimal:
    net = compute_detail_net(quantity, unit_price)
    return net * (1 + tax_percent / 100)


def compute_delivery_totals(delivery) -> dict:
    """Return net and gross totals for a delivery."""
    net = Decimal('0.00')
    gross = Decimal('0.00')
    for detail in delivery.details.select_related('tax_rate').all():
        line_net = detail.quantity * detail.unit_price
        net += line_net
        if detail.tax_rate:
            gross += line_net * (1 + detail.tax_rate.percent / 100)
        else:
            gross += line_net
    return {'net': net, 'gross': gross}

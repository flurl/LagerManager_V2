"""
Total deliveries report — grouped delivery listing with monthly/yearly totals.
"""
from decimal import Decimal

from core.models import Period
from deliveries.models import Delivery


def get_total_deliveries_report(period_id: int) -> dict:
    """
    Returns deliveries grouped by month with totals.
    """
    period = Period.objects.get(pk=period_id)
    deliveries = Delivery.objects.filter(
        period=period, is_consumption=False
    ).select_related('supplier').prefetch_related('details__tax_rate').order_by('date')

    rows = []
    monthly_totals = {}
    grand_total_net = Decimal('0.00')
    grand_total_gross = Decimal('0.00')

    for delivery in deliveries:
        net = delivery.total_net
        gross = delivery.total_gross
        month_key = delivery.date.strftime('%Y-%m')

        if month_key not in monthly_totals:
            monthly_totals[month_key] = {'net': Decimal('0.00'), 'gross': Decimal('0.00')}

        monthly_totals[month_key]['net'] += Decimal(str(net))
        monthly_totals[month_key]['gross'] += Decimal(str(gross))
        grand_total_net += Decimal(str(net))
        grand_total_gross += Decimal(str(gross))

        rows.append({
            'id': delivery.id,
            'date': delivery.date.date().isoformat(),
            'supplier': delivery.supplier.name,
            'comment': delivery.comment or '',
            'net': float(net),
            'gross': float(gross),
            'month': month_key,
        })

    return {
        'deliveries': rows,
        'monthly_totals': {
            k: {'net': float(v['net']), 'gross': float(v['gross'])}
            for k, v in monthly_totals.items()
        },
        'grand_total_net': float(grand_total_net),
        'grand_total_gross': float(grand_total_gross),
    }

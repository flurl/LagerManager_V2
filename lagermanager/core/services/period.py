"""Period date helper functions."""
from datetime import datetime

from core.models import Period


def get_period_start_end(period_id: int) -> tuple[datetime, datetime]:
    """Return (start, end) datetimes for a period."""
    period = Period.objects.get(pk=period_id)
    return period.start, period.end

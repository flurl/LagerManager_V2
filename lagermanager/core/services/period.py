import datetime

from core.models import Period


def get_period_for_datetime(dt: datetime.datetime) -> Period | None:
    """Return the Period whose start/end range contains the given datetime, or None."""
    return Period.objects.filter(start__lte=dt, end__gte=dt).first()

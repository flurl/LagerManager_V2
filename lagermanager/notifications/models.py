from django.conf import settings
from django.db import models


class StockAlertSubscription(models.Model):
    """Users who receive daily below-minimum-stock notifications."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='stock_alert_subscription',
        verbose_name='Benutzer',
    )
    active = models.BooleanField(default=True, verbose_name='Aktiv')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Lagerbestand-Alarm-Abonnement'
        verbose_name_plural = 'Lagerbestand-Alarm-Abonnements'

    def __str__(self) -> str:
        status = 'aktiv' if self.active else 'inaktiv'
        return f'{self.user} ({status})'


class Notification(models.Model):
    class Severity(models.TextChoices):
        INFO = 'info', 'Information'
        SUCCESS = 'success', 'Erfolg'
        WARNING = 'warning', 'Warnung'
        ERROR = 'error', 'Fehler'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.INFO,
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default='')
    kind = models.CharField(max_length=50, blank=True, default='')
    link = models.CharField(max_length=500, blank=True, default='')
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Benachrichtigung'
        verbose_name_plural = 'Benachrichtigungen'
        indexes = [
            models.Index(fields=['user', 'read_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

from django.apps import AppConfig


class DeliveriesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'deliveries'

    def ready(self) -> None:
        import deliveries.signals  # noqa: F401

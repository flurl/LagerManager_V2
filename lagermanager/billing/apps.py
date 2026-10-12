from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
    verbose_name = 'Fakturierung'

    def ready(self) -> None:
        # Importing the package registers the attachment kind handlers.
        import billing.attachments  # noqa: F401
        import billing.signals  # noqa: F401

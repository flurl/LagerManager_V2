from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import dj_database_url
from decouple import config

BASE_DIR: Path = Path(__file__).resolve().parent.parent

SECRET_KEY: str = config(
    'DJANGO_SECRET_KEY', default='dev-secret-key-change-in-production')
DEBUG: bool = config('DJANGO_DEBUG', default=True, cast=bool)

def _parse_list(v: str) -> list[str]:
    return [s.strip() for s in v.split(',') if s.strip()]


ALLOWED_HOSTS: list[str] = cast(
    list[str],
    config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=_parse_list),
)
SECURE_PROXY_SSL_HEADER: tuple[str, str] = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_TRUSTED_ORIGINS: list[str] = cast(
    list[str],
    config(
        'CSRF_TRUSTED_ORIGINS',
        default='http://localhost:5173,http://localhost:8000',
        cast=_parse_list,
    ),
)

INSTALLED_APPS: list[str] = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'constance',
    'constance.backends.database',
    'core',
    'inventory',
    'deliveries',
    'pos_import',
    'reports',
    'stock_count',
    'staff_consumption',
    'notifications',
    'emails',
    'billing',
    'auditlog',
]

MIDDLEWARE: list[str] = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'auditlog.middleware.AuditlogMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF: str = 'lagermanager.urls'

TEMPLATES: list[dict[str, Any]] = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION: str = 'lagermanager.wsgi.application'

DATABASES: dict[str, Any] = {
    'default': dj_database_url.config(
        default=cast(str, config(
            'DATABASE_URL', default='postgres://lagermanager:lagermanager@localhost:5432/lagermanager')),
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE: str = 'de-at'
TIME_ZONE: str = 'Europe/Vienna'
USE_I18N: bool = True
USE_TZ: bool = True

STATIC_URL: str = '/static/'
STATIC_ROOT: Path = BASE_DIR / 'staticfiles'
MEDIA_URL: str = '/media/'
MEDIA_ROOT: Path = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD: str = 'django.db.models.BigAutoField'

SIMPLE_JWT: dict[str, timedelta | bool] = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(weeks=4),
    'ROTATE_REFRESH_TOKENS': True,
}

REST_FRAMEWORK: dict[str, Any] = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 200,
}

LOGGING: dict[str, Any] = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'inventory.services.stock_calculation': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}


# Email
EMAIL_BACKEND: str = (
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend'
)
EMAIL_HOST: str = config('EMAIL_HOST', default='localhost')
EMAIL_PORT: int = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER: str = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD: str = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS: bool = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL: bool = config('EMAIL_USE_SSL', default=False, cast=bool)
DEFAULT_FROM_EMAIL: str = config('DEFAULT_FROM_EMAIL', default='noreply@example.com')
SERVER_EMAIL: str = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
DEFAULT_REPLY_TO_EMAIL: str = config('DEFAULT_REPLY_TO_EMAIL', default='')

CORS_ALLOWED_ORIGINS: list[str] = cast(
    list[str],
    config('CORS_ALLOWED_ORIGINS', default='http://localhost:5173', cast=_parse_list),
)
CORS_ALLOW_CREDENTIALS: bool = True

CONSTANCE_BACKEND: str = 'constance.backends.database.DatabaseBackend'
CONSTANCE_CONFIG_FIELDSETS: dict[str, tuple[str, ...]] = {
    'Allgemein': ('DEFAULT_TAX_RATE_ID',),
    'Dokument-Import / KI': ('GEMINI_API_KEY', 'MISTRAL_API_KEY'),
    'Unternehmen': (
        'COMPANY_NAME', 'COMPANY_ADDRESS', 'COMPANY_ZIP', 'COMPANY_CITY',
        'COMPANY_UID', 'COMPANY_IBAN', 'COMPANY_BIC', 'COMPANY_BANK',
        'COMPANY_EMAIL', 'COMPANY_PHONE',
    ),
    'Fakturierung': (
        'INVOICE_FOOTER_TEXT', 'INVOICE_PAYMENT_TERMS_DAYS',
        'DEFAULT_BILLING_TAX_RATE_ID', 'REMINDER_FEE_DEFAULT',
    ),
    'Dokumentnummern': (
        'OFFER_NUMBER_PREFIX', 'INVOICE_NUMBER_PREFIX', 'REMINDER_NUMBER_PREFIX',
    ),
    'E-Mail Vorlagen': (
        'EMAIL_SUBJECT_OFFER', 'EMAIL_BODY_OFFER',
        'EMAIL_SUBJECT_INVOICE', 'EMAIL_BODY_INVOICE',
        'EMAIL_SUBJECT_REMINDER', 'EMAIL_BODY_REMINDER',
    ),
}
CONSTANCE_CONFIG: dict[str, tuple[Any, str, type]] = {
    'DEFAULT_TAX_RATE_ID': (0, 'Standard-Steuersatz (TaxRate-ID, 0 = keiner)', int),
    'GEMINI_API_KEY': ('', 'Google Gemini API Key für den Dokumenten-Import', str),
    'MISTRAL_API_KEY': ('', 'Mistral API Key für den Dokumenten-Import (OCR)', str),
    # Billing / company issuer data (used in invoice/offer/reminder templates)
    'COMPANY_NAME': ('', 'Firmenname (Absender auf Rechnungen)', str),
    'COMPANY_ADDRESS': ('', 'Straße und Hausnummer des Unternehmens', str),
    'COMPANY_ZIP': ('', 'PLZ des Unternehmens', str),
    'COMPANY_CITY': ('', 'Ort des Unternehmens', str),
    'COMPANY_UID': ('', 'UID-Nummer des Unternehmens', str),
    'COMPANY_IBAN': ('', 'IBAN des Unternehmens', str),
    'COMPANY_BIC': ('', 'BIC des Unternehmens', str),
    'COMPANY_BANK': ('', 'Bankname des Unternehmens', str),
    'COMPANY_EMAIL': ('', 'E-Mail-Adresse des Unternehmens', str),
    'COMPANY_PHONE': ('', 'Telefonnummer des Unternehmens', str),
    'INVOICE_FOOTER_TEXT': ('', 'Fußzeilen-Text auf Rechnungen/Angeboten', str),
    'INVOICE_PAYMENT_TERMS_DAYS': (14, 'Standard-Zahlungsziel in Tagen', int),
    'DEFAULT_BILLING_TAX_RATE_ID': (0, 'Standard-Steuersatz für Faktura-Artikel (TaxRate-ID)', int),
    'REMINDER_FEE_DEFAULT': (0, 'Standard-Mahngebühr in Euro', int),
    # Document number prefixes (format: PREFIXYYMM##)
    'OFFER_NUMBER_PREFIX': ('AN', 'Nummernpräfix für Angebote', str),
    'INVOICE_NUMBER_PREFIX': ('RE', 'Nummernpräfix für Rechnungen', str),
    'REMINDER_NUMBER_PREFIX': ('MA', 'Nummernpräfix für Mahnungen', str),
    # E-Mail templates for document dispatch ({number}, {company}, {recipient_name} are replaced)
    'EMAIL_SUBJECT_OFFER': (
        'Ihr Angebot {number}',
        'E-Mail-Betreff beim Versand eines Angebots',
        str,
    ),
    'EMAIL_BODY_OFFER': (
        'Sehr geehrte Damen und Herren,\n\n'
        'anbei erhalten Sie unser Angebot {number}.\n\n'
        'Für Rückfragen stehen wir Ihnen gerne zur Verfügung.\n\n'
        'Mit freundlichen Grüßen\n{company}',
        'E-Mail-Text beim Versand eines Angebots',
        str,
    ),
    'EMAIL_SUBJECT_INVOICE': (
        'Ihre Rechnung {number}',
        'E-Mail-Betreff beim Versand einer Rechnung',
        str,
    ),
    'EMAIL_BODY_INVOICE': (
        'Sehr geehrte Damen und Herren,\n\n'
        'anbei erhalten Sie Ihre Rechnung {number}.\n\n'
        'Für Rückfragen stehen wir Ihnen gerne zur Verfügung.\n\n'
        'Mit freundlichen Grüßen\n{company}',
        'E-Mail-Text beim Versand einer Rechnung',
        str,
    ),
    'EMAIL_SUBJECT_REMINDER': (
        'Zahlungserinnerung {number}',
        'E-Mail-Betreff beim Versand einer Mahnung',
        str,
    ),
    'EMAIL_BODY_REMINDER': (
        'Sehr geehrte Damen und Herren,\n\n'
        'wir erlauben uns, Sie an die noch offene Zahlung zu erinnern '
        '(Mahnung {number}).\n\n'
        'Bitte überweisen Sie den offenen Betrag bis zum angegebenen Fälligkeitsdatum.\n\n'
        'Mit freundlichen Grüßen\n{company}',
        'E-Mail-Text beim Versand einer Mahnung',
        str,
    ),
}

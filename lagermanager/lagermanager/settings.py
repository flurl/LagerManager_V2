from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import dj_database_url
from decouple import config

BASE_DIR: Path = Path(__file__).resolve().parent.parent

SECRET_KEY: str = config(
    'DJANGO_SECRET_KEY', default='dev-secret-key-change-in-production')
DEBUG: bool = config('DJANGO_DEBUG', default=True, cast=bool)

ALLOWED_HOSTS: list[str] = ['*']

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
]

MIDDLEWARE: list[str] = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
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

STATIC_URL: str = 'static/'
MEDIA_URL: str = '/media/'
MEDIA_ROOT: Path = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD: str = 'django.db.models.BigAutoField'

SIMPLE_JWT: dict[str, timedelta] = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
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


def _parse_origins(v: str) -> list[str]:
    return [s.strip() for s in v.split(',')]


CORS_ALLOWED_ORIGINS: list[str] = cast(
    list[str],
    config('CORS_ALLOWED_ORIGINS',
           default='http://localhost:5173', cast=_parse_origins),
)
CORS_ALLOW_CREDENTIALS: bool = True

CONSTANCE_BACKEND: str = 'constance.backends.database.DatabaseBackend'
CONSTANCE_CONFIG: dict[str, tuple[Any, str, type]] = {
    'DEFAULT_TAX_RATE_ID': (0, 'Standard-Steuersatz (TaxRate-ID, 0 = keiner)', int),
    'GEMINI_API_KEY': ('', 'Google Gemini API Key für den Dokumenten-Import', str),
    'MISTRAL_API_KEY': ('', 'Mistral API Key für den Dokumenten-Import (OCR)', str),
}

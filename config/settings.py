"""
Django settings for Sistema de Gestión de Turnos.
"""

from pathlib import Path
from dotenv import load_dotenv
import os
from urllib.parse import urlparse

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde el archivo .env en la raíz del proyecto
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# dj-database-url es recomendado (Render/producción). En local puede no estar instalado.
try:
    import dj_database_url  # type: ignore
except ImportError:  # pragma: no cover
    dj_database_url = None

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

def _csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [v.strip() for v in raw.split(",") if v.strip()]

# ALLOWED_HOSTS - Configurar desde variable de entorno
# En desarrollo: ALLOWED_HOSTS=localhost,127.0.0.1
# En producción: ALLOWED_HOSTS=midominio.com,www.midominio.com
ALLOWED_HOSTS = _csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1")

# CSRF_TRUSTED_ORIGINS - importante para ngrok / dominios externos
# Podés setearlo en .env, por ejemplo:
# CSRF_TRUSTED_ORIGINS=https://*.ngrok-free.dev,https://*.ngrok-free.app
CSRF_TRUSTED_ORIGINS = _csv_env("CSRF_TRUSTED_ORIGINS", "")
# Si DEBUG está activo, permitir más hosts para desarrollo
if DEBUG:
    ALLOWED_HOSTS.extend(['*'])
    # Para que no se rompa al reiniciar ngrok (el subdominio cambia)
    CSRF_TRUSTED_ORIGINS.extend([
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://*.ngrok-free.dev",
        "https://*.ngrok-free.app",
        "https://*.ngrok.io",
    ])

# Deduplicar manteniendo orden
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

# Integraciones externas
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
MERCADOPAGO_PUBLIC_KEY = os.getenv("MERCADOPAGO_PUBLIC_KEY", "")
MP_CLIENT_ID = os.getenv("MP_CLIENT_ID", "")
MP_CLIENT_SECRET = os.getenv("MP_CLIENT_SECRET", "")
MP_REDIRECT_URI = os.getenv("MP_REDIRECT_URI", "")
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")

# Render: autoconfigurar host/CSRF si no se setean explícitamente
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
if not DEBUG:
    hostname = None
    if RENDER_EXTERNAL_HOSTNAME:
        hostname = RENDER_EXTERNAL_HOSTNAME.strip()
    elif RENDER_EXTERNAL_URL:
        try:
            hostname = urlparse(RENDER_EXTERNAL_URL).hostname
        except Exception:
            hostname = None

    if hostname:
        if hostname not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(hostname)
        origin = f"https://{hostname}"
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

    # Ajustes típicos detrás de proxy (Render termina TLS)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "True").lower() == "true"
    CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "True").lower() == "true"

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # Necesario para password reset emails
    
    # Third party apps
    'django_htmx',
    
    # Local apps
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Servir archivos estáticos en producción
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    
    # HTMX middleware
    'django_htmx.middleware.HtmxMiddleware',
    
    # Multi-tenant por subdominio
    'core.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Multi-tenant: expone complejo_actual en todos los templates
                'core.middleware.complejo_context_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database - PostgreSQL
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

# En producción (Render), usar DATABASE_URL
# En desarrollo local, usar variables individuales
db_url = os.getenv('DATABASE_URL')
if db_url:
    if dj_database_url is None:
        raise RuntimeError(
            "DATABASE_URL está configurado pero falta instalar 'dj-database-url'. "
            "Ejecutá: pip install -r requirements.txt"
        )
    DATABASES = {
        'default': dj_database_url.config(
            default=db_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # Configuración local con connection pooling optimizado
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'turnos_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'admin'),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '5432'),
            # Optimizaciones de connection pooling
            'CONN_MAX_AGE': 600,  # Reutilizar conexiones por 10 minutos
            'CONN_HEALTH_CHECKS': True,  # Verificar salud de conexiones
            'OPTIONS': {
                'connect_timeout': 10,
                'options': '-c statement_timeout=30000',  # 30 segundos timeout
            },
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'es-ar'

TIME_ZONE = 'America/Argentina/Buenos_Aires'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise configuration para servir estáticos eficientemente
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media files (uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Custom User Model
AUTH_USER_MODEL = 'core.Usuario'


# Login URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'


# Caché configuration - Redis para producción, LocMem para desarrollo
# Redis permite compartir caché entre múltiples workers de Gunicorn
REDIS_URL = os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0')

if REDIS_URL and not DEBUG:
    # Producción: Redis compartido entre workers
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': REDIS_URL,
            'TIMEOUT': 300,  # 5 minutos por defecto
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'CONNECTION_POOL_KWARGS': {
                    'max_connections': 50,
                    'retry_on_timeout': True,
                },
                'SOCKET_CONNECT_TIMEOUT': 5,
                'SOCKET_TIMEOUT': 5,
                'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
                'IGNORE_EXCEPTIONS': True,  # No romper si Redis cae
            },
            'KEY_PREFIX': 'turnos',
            'VERSION': 1,
        }
    }
else:
    # Desarrollo: LocMem (más simple para desarrollo local)
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-snowflake',
            'TIMEOUT': 300,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            }
        }
    }


# Session configuration - Redis para producción, DB para desarrollo
if REDIS_URL and not DEBUG:
    # Producción: Sessions en Redis (mucho más rápido que DB)
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
    SESSION_COOKIE_AGE = 1209600  # 2 semanas
    SESSION_SAVE_EVERY_REQUEST = False  # Solo guardar si cambió
else:
    # Desarrollo: Sessions en DB (más simple para debug)
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
    SESSION_COOKIE_AGE = 1209600


# Celery Configuration - Tareas asincrónicas
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutos máximo por tarea
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutos warning

# En Windows: usar 'threads' pool en lugar de 'prefork' para evitar PermissionError con billiard
if os.name == 'nt':  # Windows
    CELERY_WORKER_POOL = 'threads'
    CELERY_WORKER_CONCURRENCY = 4  # Menos threads en Windows para estabilidad
    CELERY_WORKER_PREFETCH_MULTIPLIER = 1
else:  # Linux/Mac
    CELERY_WORKER_POOL = 'prefork'
    CELERY_WORKER_CONCURRENCY = 4
    CELERY_WORKER_PREFETCH_MULTIPLIER = 4

CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000  # Reciclar workers después de 1000 tareas
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True


# Email configuration para recuperación de contraseñas
# En desarrollo: puedes usar Resend real o consola
# En producción: usar SMTP real (Resend, SendGrid, etc.)

# Opción de usar Resend en desarrollo (comentá para usar consola)
USE_RESEND_IN_DEV = os.getenv('USE_RESEND_IN_DEV', 'False').lower() == 'true'

if DEBUG and not USE_RESEND_IN_DEV:
    # En desarrollo: mostrar emails en consola (default)
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    # En desarrollo con Resend O en producción: usar SMTP real
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.resend.com')
    EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
    EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
    EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() == 'true'
    EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', 'resend')
    EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
    EMAIL_TIMEOUT = 10  # Timeout de 10 segundos para SMTP (falla rápido si hay problemas)

DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'onboarding@resend.dev')
EMAIL_SUBJECT_PREFIX = '[Turnos] '

# Password reset settings
PASSWORD_RESET_TIMEOUT = 86400  # 24 horas (en segundos)

# Django Sites Framework (necesario para password reset emails)
SITE_ID = 1
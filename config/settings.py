"""
Configuración del proyecto Sistema Web de Votaciones - Festival de la Leyenda Vallenata 2027.

Las credenciales y valores sensibles NO se escriben aquí: se leen desde variables de
entorno o desde un archivo ``.env`` (ignorado por git). Ver ``.env.example``.
"""
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Seguridad -------------------------------------------------------------
SECRET_KEY = config("DJANGO_SECRET_KEY", default="clave-insegura-solo-para-desarrollo")
# Por seguridad, DEBUG está apagado por defecto. Para desarrollo local: DJANGO_DEBUG=True en .env.
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)

# Fuera de desarrollo no se admite la clave por defecto: si falta DJANGO_SECRET_KEY, falla al arrancar.
if not DEBUG and SECRET_KEY == "clave-insegura-solo-para-desarrollo":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY en el archivo .env (ver .env.example).")
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# --- Aplicaciones ----------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps del proyecto
    "festival",
    "cuentas",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de datos (MySQL) -------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": config("DB_NAME", default="festival_votaciones"),
        "USER": config("DB_USER", default="festival_user"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default="3306"),
        # Cada petición se ejecuta en una transacción (RNF-02): si falla, no queda nada a medias.
        "ATOMIC_REQUESTS": True,
        "OPTIONS": {
            "charset": "utf8mb4",
            # Modo estricto: MySQL rechaza datos inválidos en vez de truncarlos.
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticación ---------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# Ingreso con correo electrónico o con nombre de usuario (CU-02).
AUTHENTICATION_BACKENDS = ["cuentas.backends.CorreoOUsuarioBackend"]

LOGIN_URL = "cuentas:login"
LOGIN_REDIRECT_URL = "festival:inicio"
LOGOUT_REDIRECT_URL = "festival:inicio"

# --- Internacionalización --------------------------------------------------
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# --- Archivos estáticos ----------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Seguridad en producción (RNF-07, riesgo R-05) --------------------------
# Se activa con DJANGO_HTTPS=True cuando el sitio se sirva por HTTPS (hosting definitivo,
# pendiente de definir con la Fundación). En desarrollo local no hace falta.
if config("DJANGO_HTTPS", default=False, cast=bool):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True

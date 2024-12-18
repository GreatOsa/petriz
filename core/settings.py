import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
import functools

from helpers.generics.utils.db import get_database_url
from helpers.fastapi import default_settings

load_dotenv(find_dotenv(".env", raise_error_if_not_found=True))


BASE_DIR = Path(__file__).resolve().parent.parent

APP = {
    "debug": str(os.getenv("DEBUG", "false")).lower() == "true",
    "title": os.getenv("FAST_API_APPLICATION_NAME"),
    "description": "Open source API provider for the SLB Glossary.",
    "version": os.getenv("FAST_API_APPLICATION_VERSION"),
    "redoc_url": None,
    "docs_url": "/api/docs",
    "openapi_url": "/openapi.json",
    "contact": {"name": "Daniel Toluwalase Afolayan"},
    "license_info": {"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
}


DEFAULT_DEPENDENCIES = []


INSTALLED_APPS = [
    "api",
    "apps.accounts",
    "apps.tokens",
    "apps.clients",
    "apps.search",
]


get_driver_postgres_url = functools.partial(
    get_database_url,
    db_type="postgresql",
    db_name=os.getenv("DB_NAME"),
    db_user=os.getenv("DB_USER"),
    db_password=os.getenv("DB_PASSWORD"),
    db_host=os.getenv("DB_HOST"),
    db_port=os.getenv("DB_PORT"),
)


SQLALCHEMY = {
    "engine": {
        "url": get_driver_postgres_url(db_driver="psycopg2"),
        "future": True,
        "connect_args": {},
    },
    "async_engine": {
        "url": get_driver_postgres_url(db_driver="asyncpg"),
        "future": True,
        "connect_args": {},
    },
    "sessionmaker": {
        "sync": {"autocommit": False, "autoflush": False, "future": True},
        "async": {
            "autocommit": False,
            "autoflush": False,
            "future": True,
            "expire_on_commit": False,
        },
    },
}


PASSWORD_SCHEMES = [
    "argon2",
    "pbkdf2_sha512",
    "md5_crypt",
]

PASSWORD_VALIDATORS = [
    *default_settings.PASSWORD_VALIDATORS,
    "apps.accounts.validators.min_password_length_validator",
]

TIMEZONE = "UTC"

AUTH_USER_MODEL = "accounts.Account"

MIDDLEWARES = [
    *default_settings.MIDDLEWARES,
    "helpers.fastapi.sqlalchemy.middlewares.AsyncSessionMiddleware",
]

OTP_LENGTH = 6

OTP_VALIDITY_PERIOD = 30 * 60

ALLOWED_HOSTS = ["*"]

BLACKLISTED_HOSTS = []

BLACKLISTED_IPS = []

MAILING = {
    "fastapi_mail": {
        "MAIL_SERVER": os.getenv("MAIL_SERVER"),
        "MAIL_PORT": os.getenv("MAIL_PORT"),
        "MAIL_STARTTLS": os.getenv("MAIL_USE_TLS"),
        "MAIL_SSL_TLS": os.getenv("MAIL_USE_SSL"),
        "MAIL_USERNAME": os.getenv("MAIL_USERNAME"),
        "MAIL_PASSWORD": os.getenv("MAIL_PASSWORD"),
        "MAIL_FROM": os.getenv("MAIL_FROM"),
        "MAIL_FROM_NAME": "Petriz",
        "USE_CREDENTIALS": True,
        "TEMPLATE_FOLDER": None,
        "SUPPRESS_SEND": False,
    }
}

RESPONSE_FORMATTER = {
    "exclude": [r"^(?!/api).*$"]  # Exclude all routes that do not start with /api
}

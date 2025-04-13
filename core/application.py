"""
Defines project setup and initialization code

All setup code should be defined in the `configure` function
"""

import anyio
import multiprocessing
import os
from contextlib import asynccontextmanager
import anyio.to_thread
import redis.asyncio as async_pyredis
import fastapi
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from helpers.fastapi.config import settings, SETTINGS_ENV_VARIABLE

NAME = "Petriz"

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
if ENVIRONMENT == "development":
    SETTINGS_MODULE = "core.settings.development_settings"
elif ENVIRONMENT == "staging":
    SETTINGS_MODULE = "core.settings.staging_settings"
elif ENVIRONMENT == "production":
    SETTINGS_MODULE = "core.settings.production_settings"
else:
    raise ValueError(f"Invalid environment: {ENVIRONMENT}")

VERSION = "1.0.0"


def set_env_vars():
    """Set environment variables required for project setup"""
    os.environ.setdefault("FAST_API_APPLICATION_NAME", NAME)
    os.environ.setdefault("FAST_API_APPLICATION_VERSION", VERSION)
    os.environ.setdefault(SETTINGS_ENV_VARIABLE, SETTINGS_MODULE)


def initialize_project() -> None:
    """Initialize/configure project"""
    set_env_vars()
    settings.configure()

    from helpers.fastapi.routing import install_router
    from .endpoints import base_router
    from helpers.fastapi.apps import discover_apps

    for app in discover_apps():
        # Ensures that models and commands defined in each app
        # are detected on project setup
        app.models
        app.commands

    # Install routers
    install_router(base_router, router_name="base_router")


def set_anyio_max_worker_threads(max_workers: int = 100) -> None:
    """Set the maximum number of threads to be used by the anyio backend"""
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = max_workers


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """Application lifespan events"""
    from helpers.fastapi.sqlalchemy.setup import engine, bind_db_to_model_base
    from helpers.fastapi.sqlalchemy.models import ModelBase
    from helpers.fastapi.apps import configure_apps
    from helpers.fastapi.requests import throttling
    from apps.search.models import execute_search_ddls
    from apps.quizzes.models import execute_quiz_ddls
    from api.caching import ORJsonCoder, request_key_builder

    set_anyio_max_worker_threads(settings.ANYIO_MAX_WORKER_THREADS)
    # Prevents deadlocks from multiple worker processes accessing lock
    # protected resources concurrently when run the application with
    # multiple workers
    with multiprocessing.Lock():
        bind_db_to_model_base(db_engine=engine, model_base=ModelBase)
        await configure_apps()
        execute_search_ddls()
        execute_quiz_ddls()

    persist_redis_data = (
        app.debug is False
    )  # Whether to clear data stored in redis in debug mode, on application exit.
    redis = async_pyredis.from_url(settings.REDIS_LOCATION, decode_responses=False)
    async with throttling.configure(
        persistent=persist_redis_data,
        redis=redis,
        prefix="petriz-api-throttle",
    ):
        try:
            FastAPICache.init(
                RedisBackend(redis),
                prefix="petriz-api-cache",
                coder=ORJsonCoder,
                key_builder=request_key_builder,
                cache_status_header="X-Cache-Status",
                expire=60 * 60,  # 1 hour
            )
            yield

        finally:
            if persist_redis_data is False and FastAPICache._backend:
                with multiprocessing.Lock():
                    await FastAPICache.clear()


def main(config: str = "APP") -> fastapi.FastAPI:
    """
    Configures and returns a FastAPI application instance
    for the project.

    :param config: name of configuration for FastAPI application in project settings
    :return: FastAPI application instance
    """
    initialize_project()

    # Ensure this environmental variables are set before anything is initialized
    # Hence, why top-level imports are avoided
    from helpers.fastapi.application import get_application

    app = get_application(**settings[config], lifespan=lifespan)
    return app

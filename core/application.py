"""
Defines project setup and initialization code

All setup code should be defined in the `configure` function
"""

import logging
import anyio
import multiprocessing
import os
from contextlib import asynccontextmanager
import anyio.to_thread
import fastapi
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_mcp import FastApiMCP

from helpers.fastapi.config import settings, SETTINGS_ENV_VARIABLE
from helpers.logging import setup_logging

NAME = "Petriz"

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
if ENVIRONMENT == "development":
    SETTINGS_MODULE = "core.settings.development"
elif ENVIRONMENT == "staging":
    SETTINGS_MODULE = "core.settings.staging"
elif ENVIRONMENT == "production":
    SETTINGS_MODULE = "core.settings.production"
else:
    raise ValueError(f"Invalid environment: {ENVIRONMENT}")

VERSION = "1.0.0"

setup_logging(log_file="logs/petriz.log")
logger = logging.getLogger(__name__)


def setup_environment_variables() -> None:
    """Set environment variables required for project setup"""
    logger.info("Setting up environment variables...")
    os.environ.setdefault("FAST_API_APPLICATION_NAME", NAME)
    os.environ.setdefault("FAST_API_APPLICATION_VERSION", VERSION)
    os.environ.setdefault(SETTINGS_ENV_VARIABLE, SETTINGS_MODULE)


def initialize_project() -> None:
    """Initialize/configure project"""
    logger.info("Initializing project...")
    setup_environment_variables()

    logger.info(f"Configuring project settings using {SETTINGS_MODULE!r} module...")
    settings.configure()

    from helpers.fastapi.routing import install_router
    from .endpoints import base_router
    from helpers.fastapi.apps import discover_apps

    for app in discover_apps():
        # Ensures that models and commands defined in each app
        # are detected on project setup
        logger.debug(f"Discovering models for app: {app.name}")
        app.models
        logger.debug(f"Discovering commands for app: {app.name}")
        app.commands

    logger.info("Installing base router...")
    install_router(base_router, router_name="base_router")


def set_anyio_max_worker_threads(max_workers: int = 100) -> None:
    """Set the maximum number of threads to be used by the anyio backend"""
    limiter = anyio.to_thread.current_default_thread_limiter()
    limiter.total_tokens = max_workers


def mount_mcp(app: fastapi.FastAPI) -> fastapi.FastAPI:
    """Mounts the FastApiMCP application to the FastAPI app"""
    logger.info("Mounting MCP application...")
    mcp_app = FastApiMCP(
        app,
        name=settings.APPLICATION_NAME,
        describe_all_responses=True,
        describe_full_response_schema=True,
        include_tags=["mcp_tools"],
    )

    mcp_app.mount(mount_path="/mcp")
    logger.info(
        f"MCP application mounted successfully. Found {len(mcp_app.tools)} tools."
    )
    return app


@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    """Application lifespan events"""
    from helpers.fastapi.sqlalchemy.setup import engine, bind_db_to_model_base
    from helpers.fastapi.sqlalchemy.models import ModelBase
    from helpers.fastapi.apps import configure_apps
    from helpers.fastapi.requests import throttling
    from apps.search.ddls import execute_search_ddls
    from apps.quizzes.ddls import execute_quiz_ddls
    from api.caching import ORJsonCoder, request_key_builder, redis

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
    async with throttling.configure(
        persistent=persist_redis_data,
        redis=redis,
        prefix="petriz-throttle",
    ):
        try:
            FastAPICache.init(
                RedisBackend(redis),
                prefix="petriz-cache",
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

    # Ensures that environmental variables are set before anything is initialized
    # Hence, why top-level imports are avoided
    from helpers.fastapi.application import (
        get_application,
        use_route_names_as_operation_ids,
    )

    app = get_application(**settings[config], lifespan=lifespan)
    app = use_route_names_as_operation_ids(app)
    return app

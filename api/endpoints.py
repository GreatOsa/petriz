import fastapi
import typing
from fastapi.responses import ORJSONResponse

from helpers.fastapi.routing import path
from helpers.fastapi import response

from .dependencies import authorization, throttling


api_router = fastapi.APIRouter(
    responses={
        400: {"model": response.ErrorSchema[None]},
        401: {"model": response.ErrorSchema[None]},
        403: {"model": response.ErrorSchema[None]},
        422: {"model": response.ErrorSchema[typing.Any]},
        404: {"model": response.ErrorSchema[None]},
        409: {"model": response.ErrorSchema[None]},
        417: {"model": response.ErrorSchema[None]},
        429: {"model": response.ErrorSchema[None]},
        500: {"model": response.ErrorSchema[None]},
    },
    default_response_class=ORJSONResponse,
)
"""Base router for the API"""

v1_router = fastapi.APIRouter(
    prefix="/v1",
)
"""Router for version 1 of the API"""


@v1_router.get(
    "",
    status_code=200,
    dependencies=[
        *throttling.ANONYMOUS_CLIENT_THROTTLES,
    ],
    tags=["api_specifics"],
)
async def health_check():
    return response.success("Server is running 🚀🚨🌐")


DEFAULT_CLIENT_DEPENDENCIES = (
    authorization.authorized_api_client_only,
    *throttling.INTERNAL_CLIENT_THROTTLES,
    *throttling.USER_CLIENT_THROTTLES,
    *throttling.PUBLIC_CLIENT_THROTTLES,
    *throttling.PARTNER_CLIENT_THROTTLES,
)


v1_router.include_router(
    path("apps.accounts.endpoints"),
    prefix="/accounts",
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)
v1_router.include_router(
    path("apps.clients.endpoints"),
    prefix="/clients",
    tags=["clients"],
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)
v1_router.include_router(
    path("apps.search.endpoints"),
    prefix="/search",
    tags=["search"],
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)
v1_router.include_router(
    path("apps.quizzes.endpoints"),
    prefix="/quizzes",
    tags=["quizzes"],
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)
v1_router.include_router(
    path("apps.audits.endpoints"),
    prefix="/audits",
    tags=["audits"],
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)


api_router.include_router(v1_router)

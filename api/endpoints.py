import fastapi

from helpers.fastapi.routing import path
from helpers.fastapi import response

from .dependencies import authorization, throttles


router = fastapi.APIRouter()


@router.get(
    "",
    status_code=200,
    dependencies=[
        *throttles.ANONYMOUS_CLIENT_THROTTLES,
    ],
)
async def health_check(request: fastapi.Request):
    return response.success("Server is running 🚀🚨🌐")


DEFAULT_CLIENT_DEPENDENCIES = (
    authorization.authorized_api_client_only,
    *throttles.INTERNAL_CLIENT_THROTTLES,
    *throttles.USER_CLIENT_THROTTLES,
    *throttles.PARTNER_CLIENT_THROTTLES,
)


router.include_router(
    path("apps.accounts.endpoints"),
    prefix="/accounts",
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)
router.include_router(
    path("apps.clients.endpoints"),
    prefix="/clients",
    tags=["clients"],
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)
router.include_router(
    path("apps.search.endpoints"),
    prefix="/search",
    tags=["search"],
    dependencies=DEFAULT_CLIENT_DEPENDENCIES,
)

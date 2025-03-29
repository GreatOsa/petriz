import fastapi

from helpers.fastapi.routing import path


base_router = fastapi.APIRouter()
"""Project's base router"""


base_router.include_router(
    path("api.endpoints", router_name="api_router"),
    prefix="/api",
)

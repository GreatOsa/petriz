import fastapi

from helpers.fastapi.routing import path
from helpers.fastapi import response

router = fastapi.APIRouter()


@router.get("", status_code=200)
async def health_check(request: fastapi.Request):
    return response.success("Server is running 🚀🚨🌐")


router.include_router(
    path("apps.accounts.endpoints"), prefix="/accounts",
)
router.include_router(
    path("apps.clients.endpoints"), prefix="/clients", tags=["clients"],
)
router.include_router(
    path("apps.search.endpoints"), prefix="/search", tags=["search"],
)

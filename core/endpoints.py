import fastapi

from helpers.fastapi.routing import path


router = fastapi.APIRouter()
"""Project's base router"""

router.include_router(path("api.endpoints"), prefix="/api/v1")

from starlette.requests import HTTPConnection

from helpers.fastapi.exceptions.capture import exception_captured_handler, ExceptionCaptor
from helpers.fastapi.response.format import json_httpresponse_formatter


async def formatted_exception_captured_handler(
    connection: HTTPConnection,
    exc: ExceptionCaptor.ExceptionCaptured,
):
    """Handles `ExceptionCaptured` exceptions and formats the error response into structured format"""
    response = await exception_captured_handler(connection, exc)

    if response.headers.get("Content-Type") == "application/json":
        return await json_httpresponse_formatter(response) # type: ignore
    return response

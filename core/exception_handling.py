from starlette.requests import HTTPConnection

from helpers.fastapi.exceptions.capture import exception_captured_handler
from helpers.fastapi.response.format import json_httpresponse_formatter


async def formatted_exception_captured_handler(
    connection: HTTPConnection,
    exc: Exception,
):
    """Handles `ExceptionCaptured` exceptions and formats the error response into structured format"""
    error_response = await exception_captured_handler(connection, exc)

    if error_response.headers.get("Content-Type") == "application/json":
        return await json_httpresponse_formatter(error_response)
    return error_response

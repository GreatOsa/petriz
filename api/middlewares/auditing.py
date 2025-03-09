import typing
import fastapi
from starlette.responses import (
    Response,
    StreamingResponse as StarletteStreamingResponse,
)
from fastapi.responses import StreamingResponse as FastAPIStreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from helpers.fastapi.utils.requests import get_ip_address
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.config import settings
from apps.accounts.models import Account
from apps.clients.models import APIClient
from apps.audits.schemas import AuditLogEntryCreateSchema
from apps.audits.models import ActionStatus, AuditLogEntry
from api.dependencies.auditing import RequestEvent


SENSITIVE_HEADERS = {header.lower() for header in settings.SENSITIVE_HEADERS}


def _clean_headers(headers: dict) -> dict:
    """Remove sensitive headers from the request or response headers."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in SENSITIVE_HEADERS
    }


async def get_api_client_from_request(
    request: fastapi.Request,
) -> typing.Optional[APIClient]:
    """Get the API client from the request."""
    api_client = getattr(request.state, "client", None)
    if not isinstance(api_client, APIClient):
        return None
    return api_client


async def get_account_from_request(
    request: fastapi.Request,
) -> typing.Optional[Account]:
    """Get the account information from the request."""
    account = getattr(request.state, "user", None)
    if not isinstance(account, Account):
        return None
    return account


async def _create_audit_logs(
    session: AsyncSession,
    request_events: list[RequestEvent],
    metadata: dict,
    status: ActionStatus,
    user_agent: str,
    ip_address: str,
    api_client: typing.Optional[APIClient],
    account: typing.Optional[Account],
) -> None:
    """
    Create audit logs in batch.

    :param session: The database session.
    :param request_events: The request events to log.
    :param metadata: The metadata to log.
    :param status: The status of the request.
    :param user_agent: The user agent of the request.
    :param ip_address: The IP address of the request.
    :param api_client: The API client associated with the request.
    :param account: The account associated with the request.
    """
    entries = [
        AuditLogEntryCreateSchema(
            event=request_event["event"],
            user_agent=user_agent,
            ip_address=ip_address,
            actor_uid=api_client.uid if api_client else None,
            actor_type="api_client" if api_client else None,
            account_email=account.email if account else None,
            account_uid=account.uid if account else None,
            target=request_event["target"],
            target_uid=request_event["target_uid"],
            description=request_event["description"],
            status=status,
            data=metadata,
        ).model_dump()
        for request_event in request_events
    ]

    await session.run_sync(
        lambda s: s.bulk_insert_mappings(AuditLogEntry, entries, render_nulls=True)
    )
    await session.commit()


async def RequestEventLogMiddleware(
    request: fastapi.Request,
    call_next,
):
    """Logs the request event"""
    if not settings.LOG_REQUEST_EVENTS:
        return await call_next(request)

    metadata = {
        "request": {
            "method": request.method,
            "url": str(request.url),
            "query_params": dict(request.query_params),
            "headers": _clean_headers(dict(request.headers)),
            "body": None,
        },
    }

    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            metadata["request"]["body"] = (await request.body()).decode()
        except Exception:
            metadata["request"]["body"] = "[Unable to decode body]"

    try:
        response: Response = await call_next(request)
        status = (
            ActionStatus.SUCCESS if response.status_code < 400 else ActionStatus.ERROR
        )

        metadata["response"] = {
            "status_code": response.status_code,
            "headers": _clean_headers(dict(response.headers)),
            "content": None,
        }

        if not isinstance(
            response, (StarletteStreamingResponse, FastAPIStreamingResponse)
        ):
            try:
                metadata["response"]["content"] = response.body.decode()
            except Exception:
                metadata["response"]["content"] = "[Unable to decode body]"

    except Exception as exc:
        status = ActionStatus.ERROR
        metadata["error"] = str(exc)
        raise exc from None
    finally:
        request_events: typing.List[RequestEvent] = getattr(
            request.state, "events", None
        ) or [
            RequestEvent(
                event=request.method,
                target=str(request.url),
                target_uid=None,
                description=f"{request.method} request to {request.url}",
            ),
        ]

        async with get_async_session() as session:
            await _create_audit_logs(
                session=session,
                request_events=request_events,
                metadata=metadata,
                status=status,
                user_agent=request.headers.get("user-agent"),
                ip_address=get_ip_address(request),
                api_client=await get_api_client_from_request(request),
                account=await get_account_from_request(request),
            )

    return response

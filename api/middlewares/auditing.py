import typing
import fastapi

from helpers.fastapi.utils.requests import get_ip_address
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.config import settings
from apps.accounts.models import Account
from apps.clients.models import APIClient
from apps.audits.schemas import AuditLogEntryCreateSchema
from apps.audits.models import ActionStatus
from apps.audits.crud import create_audit_log_entry


def get_api_client_from_request(request: fastapi.Request) -> typing.Optional[APIClient]:
    """Get the API client from the request."""
    api_client = getattr(request.state, "client", None)
    if not isinstance(api_client, APIClient):
        return None
    return api_client


def get_account_from_request(request: fastapi.Request) -> typing.Optional[Account]:
    """Get the account information from the request."""
    account = getattr(request.state, "user", None)
    if not isinstance(account, Account):
        return None
    return account


def _clean_headers(headers: typing.Dict[str, str]) -> typing.Dict[str, str]:
    """Remove sensitive headers from the request."""
    sensitive_headers = [header.lower() for header in settings.SENSITIVE_HEADERS]
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in sensitive_headers
    }


async def RequestEventLogMiddleware(
    request: fastapi.Request,
    call_next,
):
    """Log an event."""
    user_agent = request.headers.get("user-agent", None)
    ip_address = get_ip_address(request)
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

    exception = None
    try:
        response: fastapi.Response = await call_next(request)
    except Exception as exc:
        exception = exc
        status = ActionStatus.ERROR
        response = None
        metadata["error"] = str(exc)

    request_event: typing.Dict[str, typing.Any] = getattr(request.state, "event", None)
    if isinstance(request_event, dict):
        event = request_event["event"]
        target = request_event.get("target", None)
        target_uid = request_event.get("target_uid", None)
        description = request_event.get("description", None)
    else:
        event = request.method
        target = str(request.url)
        target_uid = None
        description = f"{request.method} request to {request.url}"

    api_client = get_api_client_from_request(request)
    account = get_account_from_request(request)

    if response:
        status = (
            ActionStatus.SUCCESS if response.status_code < 400 else ActionStatus.ERROR
        )
        metadata["response"] = {
            "status_code": response.status_code,
            "headers": _clean_headers(dict(response.headers)),
            "content": None,
        }

        if not isinstance(response, fastapi.responses.StreamingResponse):
            try:
                metadata["response"]["content"] = response.body.decode()
            except Exception:
                metadata["response"]["content"] = "[Unable to decode response body]"

    # Do not use request session because an error might have occurred before this point
    # preventing the changes to the session from being committed or causing it to close.
    # if we reuse the session, the changes that were not committed will be committed here,
    #  which lead to unexpected actions, especially if the session was not rolled back.
    # Also attempting to commit a closed session will raise an error.
    # Instead, create a new session and commit the changes.
    async with get_async_session() as session:
        schema = AuditLogEntryCreateSchema(
            event=event,
            user_agent=user_agent,
            ip_address=ip_address,
            actor_uid=api_client.uid if api_client else None,
            actor_type="api_client" if api_client else None,
            account_email=account.email if account else None,
            account_uid=account.uid if account else None,
            target=target,
            target_uid=str(target_uid),
            description=description,
            status=status,
            data=metadata,
        )
        await create_audit_log_entry(
            session,
            **schema.model_dump(),
        )
        await session.commit()

    if exception:
        raise exception
    return response

import typing
import pydantic
from starlette.requests import HTTPConnection, empty_send
from starlette.types import ASGIApp, Send, Scope, Receive, Message
from starlette.datastructures import Headers
from sqlalchemy.ext.asyncio import AsyncSession

from helpers.fastapi.utils.requests import get_ip_address
from helpers.fastapi.sqlalchemy.setup import get_async_session
from helpers.fastapi.config import settings
from helpers.fastapi.middlewares.core import urlstring_to_re
from apps.accounts.models import Account
from apps.clients.models import APIClient
from apps.audits.schemas import AuditLogEntryCreateSchema
from apps.audits.models import ActionStatus, AuditLogEntry
from api.dependencies.auditing import ConnectionEvent


SENSITIVE_HEADERS = {header.lower() for header in settings.SENSITIVE_HEADERS}


def _clean_headers(headers: typing.Mapping[str, str]) -> dict:
    """Remove sensitive headers from the connection or response headers."""
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in SENSITIVE_HEADERS
    }


async def get_api_client_from_connection(
    connection: HTTPConnection,
) -> typing.Optional[APIClient]:
    """Get the API client from the connection."""
    api_client = getattr(connection.state, "client", None)
    if not isinstance(api_client, APIClient):
        return None
    return api_client


async def get_account_from_connection(
    connection: HTTPConnection,
) -> typing.Optional[Account]:
    """Get the account information from the connection."""
    account = getattr(connection.state, "user", None)
    if not isinstance(account, Account):
        return None
    return account


async def _create_audit_logs(
    session: AsyncSession,
    connection_events: typing.Sequence[ConnectionEvent],
    metadata: typing.MutableMapping[str, typing.Any],
    status: ActionStatus,
    user_agent: typing.Optional[str],
    ip_address: typing.Optional[pydantic.IPvAnyAddress],
    api_client: typing.Optional[APIClient],
    account: typing.Optional[Account],
) -> None:
    """
    Create audit logs in batch.

    :param session: The database session.
    :param connection_events: The connection events to log.
    :param metadata: The metadata to log.
    :param status: The status of the connection.
    :param user_agent: The user agent of the connection.
    :param ip_address: The IP address of the connection.
    :param api_client: The API client associated with the connection.
    :param account: The account associated with the connection.
    """
    entries = [
        AuditLogEntryCreateSchema(
            event=request_event["event"],
            user_agent=user_agent,
            ip_address=ip_address,  # type: ignore
            actor_uid=api_client.uid if api_client else None,
            actor_type="api_client" if api_client else None,
            account_email=account.email if account else None,
            account_uid=account.uid if account else None,
            target=request_event["target"],
            target_uid=request_event["target_uid"],
            description=request_event["description"],
            status=status,
            data=dict(metadata),
        ).model_dump()
        for request_event in connection_events
    ]

    await session.run_sync(
        lambda s: s.bulk_insert_mappings(AuditLogEntry, entries, render_nulls=True)  # type: ignore
    )
    await session.commit()


class ConnectionEventLogResponder:
    """
    Responder to log connection events attached to the connection.
    """

    def __init__(
        self,
        app: ASGIApp,
        metadata: typing.Optional[typing.MutableMapping[str, typing.Any]] = None,
    ) -> None:
        """
        Initialize the responder.

        :param app: The ASGI application.
        :param metadata: Base metadata to log.
        """
        self.app = app
        self.send = empty_send
        self.status = ActionStatus.ERROR  # Assume error until proven otherwise
        self.metadata = metadata or {}
        self.exception = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        connection = HTTPConnection(scope, receive)
        if settings.LOG_CONNECTION_EVENTS is False:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = connection.url.path
        query_params = dict(connection.query_params)
        headers = _clean_headers(connection.headers)
        self.metadata["connection"] = {
            "method": method,
            "url": path,
            "query_params": query_params,
            "headers": headers,
            "body": None,
        }

        try:
            await self.app(scope, receive, self.send_response)
        except Exception as exc:
            self.exception = exc
            self.metadata["error"] = str(exc)

        connection_events: typing.Optional[typing.Sequence[ConnectionEvent]] = getattr(
            connection.state, "events", None
        )
        if not connection_events:
            connection_events = [
                ConnectionEvent(
                    event=method,
                    target=path,
                    target_uid=None,
                    description=f"{method} connection to {path}",
                ),
            ]

        user_agent = headers.get("user-agent")
        ip_address = get_ip_address(connection)
        api_client = await get_api_client_from_connection(connection)
        account = await get_account_from_connection(connection)
        async with get_async_session() as session:
            await _create_audit_logs(
                session=session,
                connection_events=connection_events,
                metadata=self.metadata,
                status=self.status,
                user_agent=user_agent,
                ip_address=ip_address,
                api_client=api_client,
                account=account,
            )

        if self.exception:
            raise self.exception

    async def send_response(self, message: Message) -> None:
        message_type = message["type"]
        if message_type == "http.response.start":
            self.metadata["response"] = {
                "status_code": message["status"],
                "headers": _clean_headers(dict(Headers(raw=message["headers"]))),
                "body": None,
            }
            self.status = (
                ActionStatus.SUCCESS
                if 200 <= message["status"] < 400
                else ActionStatus.ERROR
            )

        elif message_type == "http.response.body":
            body = message.get("body", b"")
            if not body or "response" not in self.metadata:
                await self.send(message)
                return

            if not self.metadata["response"].get("body", None):
                self.metadata["response"]["body"] = [body.decode()]
            else:
                self.metadata["response"]["body"].append(body.decode())

        await self.send(message)


class ConnectionEventLogMiddleware:
    """
    Middleware to log connection events attached to the connection.
    """

    def __init__(
        self, app: ASGIApp, exclude: typing.Optional[typing.Sequence[str]] = None
    ):
        self.app = app
        self.exclude = exclude or []
        self.excluded_paths_patterns = [urlstring_to_re(path) for path in self.exclude]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if any(pattern.match(path) for pattern in self.excluded_paths_patterns):
            await self.app(scope, receive, send)
            return
        responder = ConnectionEventLogResponder(app=self.app)
        await responder(scope, receive, send)

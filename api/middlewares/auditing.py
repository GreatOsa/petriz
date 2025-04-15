import typing
import gzip
import orjson
import base64
import pydantic
from starlette.requests import HTTPConnection, empty_send, empty_receive
from starlette.types import ASGIApp, Send, Scope, Receive, Message
from starlette.datastructures import Headers
from sqlalchemy.ext.asyncio import AsyncSession

from helpers.fastapi.utils.requests import get_ip_address
from helpers.fastapi.utils.sync import sync_to_async
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


@sync_to_async
def compress_data(data: typing.Any) -> str:
    """
    Compress data using gzip and encode it to base64.

    :param data: The data to compress.
    :return: The compressed and base64-encoded data.
    """
    if not isinstance(data, (bytes, bytearray)):
        bytes_data = orjson.dumps(data)
    else:
        bytes_data = data

    compressed = gzip.compress(bytes_data)
    return base64.b64encode(compressed).decode("utf-8")


@sync_to_async
def decompress_data(data: str) -> typing.Any:
    """
    Decompress data from base64 and gzip.

    :param data: The base64-encoded compressed data.
    :return: The decompressed data.
    """
    compressed = base64.b64decode(data.encode("utf-8"))
    decompressed = gzip.decompress(compressed)
    return orjson.loads(decompressed.decode("utf-8"))


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
        include_request: bool = True,
        include_response: bool = True,
        compress_body: bool = False,
    ) -> None:
        """
        Initialize the responder.

        :param app: The ASGI application.
        :param metadata: Base metadata to log.
        :param include_request: Whether to include the request data in the log.
        :param include_response: Whether to include the response data in the log.
        :param compress_body: Whether to compress the request and response body in log data.
        """
        self.app = app
        self.send = empty_send
        self.receive = empty_receive
        self.status = ActionStatus.ERROR  # Assume error until proven otherwise
        self.metadata = metadata or {}
        self.exception = None
        self.include_request = include_request
        self.include_response = include_response
        self.compress_body = compress_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        self.receive = receive
        if settings.LOG_CONNECTION_EVENTS is False:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        path = scope["path"]
        connection = HTTPConnection(scope, receive)
        headers = _clean_headers(connection.headers)

        if self.include_request:
            query_params = dict(connection.query_params)
            self.metadata["request"] = {
                "method": method,
                "url": path,
                "query_params": query_params,
                "headers": headers,
                "body": None,
            }

        if self.include_response:
            self.metadata["response"] = {
                "status_code": None,
                "headers": None,
                "body": None,
            }

        try:
            await self.app(scope, self.receive_request, self.send_response)
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

    async def receive_request(self) -> Message:
        message = await self.receive()
        if not self.include_request:
            return message

        if message["type"] == "http.request":
            body = message.get("body", b"")
            if body:
                if self.compress_body:
                    body_data = await compress_data(body)
                else:
                    body_data = body.decode("utf-8")

                if self.metadata["request"].get("body", None) is None:
                    self.metadata["request"]["body"] = [body_data]
                else:
                    self.metadata["request"]["body"].append(body_data)
        return message

    async def send_response(self, message: Message) -> None:
        if not self.include_response:
            await self.send(message)
            return

        message_type = message["type"]
        if message_type == "http.response.start":
            self.metadata["response"]["status_code"] = message["status"]
            self.metadata["response"]["headers"] = _clean_headers(
                dict(Headers(raw=message["headers"]))
            )
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

            if self.compress_body:
                body_data = await compress_data(body)
            else:
                body_data = body.decode("utf-8")

            if self.metadata["response"].get("body", None) is None:
                self.metadata["response"]["body"] = [body_data]
            else:
                self.metadata["response"]["body"].append(body_data)

        await self.send(message)


class ConnectionEventLogMiddleware:
    """
    Middleware to log connection events attached to the connection.
    """

    def __init__(
        self,
        app: ASGIApp,
        excluded_paths: typing.Optional[typing.Sequence[str]] = None,
        included_paths: typing.Optional[typing.Sequence[str]] = None,
        include_request: bool = True,
        include_response: bool = True,
        compress_body: bool = False,
    ):
        """
        Initialize the middleware.

        :param app: The ASGI application.
        :param excluded_paths: List of (regex type) paths to exclude from logging.
        :param included_paths: List of (regex type) paths to include in logging.
        :param compress_body: Whether to compress the request and response body in log data.
            This is useful for making log dat for large payloads smaller.
        :param include_request: Whether to include the request data in the log.
        :param include_response: Whether to include the response data in the log.
        """
        if excluded_paths and included_paths:
            raise ValueError("Cannot specify both 'exclude' and 'include' paths.")

        self.app = app
        self.included_paths_patterns = (
            [urlstring_to_re(path) for path in included_paths] if included_paths else []
        )
        self.excluded_paths_patterns = (
            [urlstring_to_re(path) for path in excluded_paths] if excluded_paths else []
        )
        self.include_request = include_request
        self.include_response = include_response
        self.compress_body = compress_body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if self.excluded_paths_patterns and any(
            pattern.match(path) for pattern in self.excluded_paths_patterns
        ):
            await self.app(scope, receive, send)
            return
        if self.included_paths_patterns and not any(
            pattern.match(path) for pattern in self.included_paths_patterns
        ):
            await self.app(scope, receive, send)
            return

        responder = ConnectionEventLogResponder(
            app=self.app,
            include_request=self.include_request,
            include_response=self.include_response,
            compress_body=self.compress_body,
        )
        await responder(scope, receive, send)

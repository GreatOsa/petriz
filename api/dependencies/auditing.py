import typing
import fastapi
import fastapi.params
from starlette.requests import HTTPConnection

from helpers.fastapi.config import settings


class ConnectionEvent(typing.TypedDict):
    event: str
    target: typing.Optional[typing.Any]
    target_uid: typing.Optional[typing.Any]
    description: typing.Optional[str]


def event(
    event: str,
    /,
    target: typing.Optional[typing.Any] = None,
    target_uid: typing.Optional[typing.Any] = None,
    description: typing.Optional[str] = None,
    event_dependency_suffix: str = "request",
) -> fastapi.params.Depends:
    """
    Mark the connection for audit logging by attaching the event data to the connection state.

    Endeavour to make this dependency the first in the chain of dependencies.
    This ensures that the event data is attached to the connection state before any other dependencies are resolved.
    Hence, errors that occur during the resolution of other dependencies can still be logged with the correct event data.

    Example:
    ```python
    @app.post(
        "/users/",
        dependencies=[
            event("user_create", target="user")
        ]
    )
    async def create_user(user: UserCreate) -> User:
        ...

    @app.get(
        "/users/{user_id}/",
        dependencies=[
            event(
                "user_retrieve",
                target="user",
                target_uid=fastapi.Path(alias="user_id")
            )
        ]
    )
    async def retrieve_user(user_id: str = fastapi.Path(...)) -> User:
        ...
    ```

    :param event: The event or action that occurred. E.g. user_login, user_logout, GET, POST, etc.
    :param target: The target of the event. E.g. user, post, comment, etc.
        This can also be a another fastapi dependency, path, query, etc.
        that resolves to the target.
    :param target_uid: The unique ID of the target. This can also be another fastapi
        dependency, path, query, etc. that resolves to the target ID.
    :param description: A description of the event or action.
    :return: A fastapi dependency that attaches the event data to the connection state.
    """

    async def dependency(
        connection: HTTPConnection,
        target: typing.Optional[typing.Any] = target,
        target_uid: typing.Optional[typing.Any] = target_uid,
    ) -> HTTPConnection:
        if not settings.LOG_CONNECTION_EVENTS:
            return connection

        event_data = ConnectionEvent(
            event=event,
            target=target,
            target_uid=target_uid,
            description=description,
        )
        connection_events = getattr(connection.state, "events", [])
        setattr(connection.state, "events", [*connection_events, event_data])
        return connection

    dependency.__name__ = f"{event}_{event_dependency_suffix}"
    return fastapi.Depends(dependency)

import typing
import fastapi
import fastapi.params


def event(
    event: str,
    /,
    target: typing.Optional[typing.Any] = None,
    target_uid: typing.Optional[typing.Any] = None,
    description: typing.Optional[str] = None,
) -> fastapi.params.Depends:
    """
    Mark the request for audit logging by attaching the event data to the request state.

    Endeavour to make this dependency the first in the chain of dependencies.
    This ensures that the event data is attached to the request state before any other dependencies are resolved.
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
    :return: A fastapi dependency that attaches the event data to the request state.
    """

    async def _dependency(
        request: fastapi.Request,
        target: typing.Optional[typing.Any] = target,
        target_uid: typing.Optional[typing.Any] = target_uid,
    ) -> fastapi.Request:
        data = {
            "event": event,
            "target": target,
            "target_uid": target_uid,
            "description": description,
        }
        setattr(request.state, "event", data)
        return request

    _dependency.__name__ = f"{event}_request"
    return fastapi.Depends(_dependency)

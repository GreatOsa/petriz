import typing
import fastapi

from helpers.fastapi.requests.query import (
    QueryParamNotSet,
    ParamNotSet,
    OrderingExpressions,
    ordering_query_parser_factory,
)
from .models import AuditLogEntry


_T = typing.TypeVar("_T", covariant=True)


def query_parser_factory(
    param_name: str,
    description: str,
    process_value: typing.Optional[typing.Callable[[str], _T]] = None,
):
    async def query_parser(
        value: typing.Annotated[
            typing.Optional[str],
            fastapi.Query(
                description=description,
                alias=param_name,
                alias_priority=1,
            ),
        ] = None,
    ) -> typing.Union[str, _T, QueryParamNotSet]:
        if value is None:
            return ParamNotSet
        if process_value is not None:
            return process_value(value)
        return value.strip() or ParamNotSet

    return query_parser


Event: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="event",
            description="The event or action that occurred. E.g. user_login, user_logout, GET, POST, etc.",
        )
    ),
]

UserAgent: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="user_agent",
            description="The user agent of the source of the event.",
        )
    ),
]

IPAddress: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="ip_address",
            description="The IP address of the source of the event.",
        )
    ),
]

ActorUID: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="actor_uid",
            description="The unique ID of the actor who performed the action. Can be API client UID, User UID etc.",
        )
    ),
]

ActorType: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="actor_type",
            description="The type of the actor who performed the action.",
        )
    ),
]

AccountEmail: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="account_email",
            description="The email of the account that performed the action.",
        )
    ),
]

AccountUID: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="account_uid",
            description="The unique ID of the account that performed the action.",
        )
    ),
]

Target: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="target",
            description="A name for the target of the action. Can be a resource URL, etc.",
        )
    ),
]

TargetUID: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="target_uid",
            description="The unique ID of the target, if any.",
        )
    ),
]

Status: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(
        query_parser_factory(
            param_name="status",
            description="The status of the action.",
        )
    ),
]

audit_logs_ordering_query_parser = ordering_query_parser_factory(
    AuditLogEntry,
    allowed_columns={
        "created_at",
        "event",
        "actor_type",
        "account_email",
        "target",
        "status",
    },
)

AuditLogOrdering: typing.TypeAlias = typing.Annotated[
    typing.Union[OrderingExpressions[AuditLogEntry], QueryParamNotSet],
    fastapi.Depends(audit_logs_ordering_query_parser),
]


__all__ = [
    "Event",
    "UserAgent",
    "IPAddress",
    "ActorUID",
    "ActorType",
    "AccountEmail",
    "AccountUID",
    "Target",
    "TargetUID",
    "Status",
    "AuditLogOrdering",
]

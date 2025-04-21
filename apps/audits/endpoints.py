from turtle import st
import fastapi
import typing
from annotated_types import Le
from fastapi_cache.decorator import cache

from helpers.fastapi.dependencies.connections import AsyncDBSession
from helpers.fastapi import response
from helpers.fastapi.response.pagination import paginated_data, PaginatedResponse
from helpers.fastapi.requests.query import (
    Limit,
    Offset,
    clean_params,
)
from helpers.fastapi.dependencies.access_control import admin_user_only
from api.dependencies.authorization import (
    internal_api_clients_only,
    permissions_required,
)
from api.dependencies.authentication import authentication_required
from helpers.fastapi.auditing.dependencies import event
from apps.search.query import TimestampGte, TimestampLte
from . import schemas, crud
from .query import (
    Event,
    UserAgent,
    IPAddress,
    ActorUID,
    ActorType,
    AccountEmail,
    AccountUID,
    Target,
    TargetUID,
    Status,
    AuditLogOrdering,
)


router = fastapi.APIRouter(
    tags=["audits"],
    dependencies=[
        event(
            "audits_access",
            description="Access audits endpoints.",
        ),
        internal_api_clients_only,
        authentication_required,
        admin_user_only,
    ],
)


@router.get(
    "/logs",
    description="Retrieve audit logs.",
    dependencies=[
        event(
            "audit_logs_retrieve",
            description="Retrieve audit logs.",
        ),
        permissions_required(
            "audit_log_entries::*::list",
        ),
    ],
    response_model=PaginatedResponse[schemas.AuditLogEntrySchema], # type: ignore
    status_code=200,
)
@cache(namespace="audit_logs", expire=60)
async def retrieve_audit_logs(
    request: fastapi.Request,
    session: AsyncDBSession,
    event: Event,
    user_agent: UserAgent,
    ip_address: IPAddress,
    actor_uid: ActorUID,
    actor_type: ActorType,
    account_email: AccountEmail,
    account_uid: AccountUID,
    target: Target,
    target_uid: TargetUID,
    status: Status,
    ordering: AuditLogOrdering,
    timestamp_gte: TimestampGte,
    timestamp_lte: TimestampLte,
    limit: typing.Annotated[Limit, Le(100)] = 100,
    offset: Offset = 0,
) -> fastapi.Response:
    """Retrieve audit logs."""
    params = clean_params(
        event=event,
        user_agent=user_agent,
        ip_address=ip_address,
        actor_uid=actor_uid,
        actor_type=actor_type,
        account_email=account_email,
        account_uid=account_uid,
        target=target,
        target_uid=target_uid,
        status=status,
        ordering=ordering,
        limit=limit,
        offset=offset,
        timestamp_gte=timestamp_gte,
        timestamp_lte=timestamp_lte,
    )
    audit_logs = await crud.retrieve_audit_log_entries(session, **params)  # type: ignore
    response_data = [
        schemas.AuditLogEntrySchema.model_validate(audit_log_entry)
        for audit_log_entry in audit_logs
    ]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )

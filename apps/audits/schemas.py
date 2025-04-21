import typing
import pydantic

from .models import ActionStatus


class AuditLogEntryBaseSchema(pydantic.BaseModel):
    """Base schema for an audit log entry."""

    event: typing.Annotated[
        str,
        pydantic.StringConstraints(
            max_length=255,
            to_lower=True,
            strip_whitespace=True,
        ),
    ]
    user_agent: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=255)]
    ]
    ip_address: typing.Optional[pydantic.IPvAnyAddress]
    actor_uid: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=50)]
    ]
    actor_type: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=50)]
    ]
    account_email: typing.Optional[pydantic.EmailStr]
    account_uid: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=50)]
    ]
    target: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=255)]
    ]
    target_uid: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=50)]
    ]
    description: typing.Optional[
        typing.Annotated[str, pydantic.StringConstraints(max_length=500)]
    ]
    status: typing.Optional[ActionStatus]
    metadata: typing.Optional[typing.Dict[str, pydantic.JsonValue]] = (
        pydantic.Field(
            default=None,
            serialization_alias="metadata",
            validation_alias=pydantic.AliasChoices(
                "extradata",
                "metadata",
            ),
            description="Additional metadata for the audit log entry.",
        )
    )


class AuditLogEntryCreateSchema(AuditLogEntryBaseSchema):
    """Schema for creating an audit log entry."""

    pass


class AuditLogEntrySchema(AuditLogEntryBaseSchema):
    """Schema for an audit log entry serialization/deserialization."""

    uid: typing.Annotated[pydantic.StrictStr, pydantic.StringConstraints(max_length=50)]
    created_at: pydantic.AwareDatetime
    updated_at: typing.Optional[pydantic.AwareDatetime]

    class Config:
        from_attributes = True

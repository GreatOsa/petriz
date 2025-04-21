import pydantic
import typing
from annotated_types import MaxLen, MinLen

from helpers.fastapi.utils import timezone
from helpers.generics.pydantic import partial
from .models import ClientType
from .permissions import PermissionSchema


class APIKeyBaseSchema(pydantic.BaseModel):
    """API Key base schema."""

    active: pydantic.StrictBool = pydantic.Field(
        description="Is the API Key active and usable?"
    )
    valid_until: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None, description="API Key expiration date and time"
    )


class APIKeySchema(APIKeyBaseSchema):
    """API Key schema. For serialization purposes only."""

    uid: pydantic.StrictStr = pydantic.Field(description="API Key UID")
    secret: pydantic.StrictStr = pydantic.Field(description="API Key secret")
    valid: pydantic.StrictBool = pydantic.Field(
        description="Is the API Key valid or expired?"
    )
    created_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="API Key creation date and time"
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="API Key last update date and time"
    )

    class Config:
        from_attributes = True


@partial
class APIKeyUpdateSchema(APIKeyBaseSchema):
    @pydantic.field_validator("valid_until", mode="after")
    @classmethod
    def validate_valid_until(cls, value: pydantic.AwareDatetime):
        value = value.astimezone(timezone.get_current_timezone())
        if value <= timezone.now():
            raise ValueError("Value must be set to a future datetime.")
        return value


class APIClientBaseSchema(pydantic.BaseModel):
    """API Client base schema."""

    name: typing.Optional[
        typing.Annotated[
            str,
            pydantic.StringConstraints(
                strip_whitespace=True,
                to_lower=True,
                min_length=6,
                max_length=50,
            ),
        ]
    ] = pydantic.Field(
        default=None,
        description="API Client name",
    )
    description: typing.Optional[pydantic.StrictStr] = pydantic.Field(
        default=None, max_length=500, description="API Client description"
    )


class APIClientCreateSchema(APIClientBaseSchema):
    """API Client creation schema."""

    client_type: ClientType = pydantic.Field(description="API Client type")

    @pydantic.field_validator("client_type", mode="before")
    @classmethod
    def validate_client_type(cls, value: typing.Any):
        if isinstance(value, str):
            return value.lower()
        return value


class APIClientSimpleSchema(APIClientBaseSchema):
    """API Client simple schema. For serialization purposes only."""

    uid: pydantic.StrictStr = pydantic.Field(description="API Client UID")
    client_type: ClientType = pydantic.Field(description="API Client type")

    @pydantic.field_validator("client_type", mode="before")
    @classmethod
    def validate_client_type(cls, value: typing.Any):
        if isinstance(value, str):
            return value.lower()
        return value

    class Config:
        from_attributes = True


class APIClientSchema(APIClientBaseSchema):
    """API Client schema. For serialization purposes only."""

    uid: pydantic.StrictStr = pydantic.Field(description="API Client UID")
    client_type: ClientType = pydantic.Field(description="API Client type")
    api_key: typing.Optional[APIKeySchema] = pydantic.Field(
        default=None, description="API Key"
    )
    is_disabled: pydantic.StrictBool = pydantic.Field(
        description="Is the API Client disabled?"
    )
    permissions: typing.List[PermissionSchema] = pydantic.Field(
        default_factory=list, description="API Client permissions"
    )
    permissions_modified_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Latest API Client permission modification date and time"
    )
    created_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="API Client creation date and time"
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="API Client last update date and time"
    )

    class Config:
        from_attributes = True

    @pydantic.field_validator("client_type", mode="before")
    @classmethod
    def validate_client_type(cls, value: typing.Any):
        if isinstance(value, str):
            return value.lower()
        return value

    @pydantic.field_validator("permissions", mode="before")
    @classmethod
    def validate_permissions(cls, value: typing.Any):
        if isinstance(value, (list, set, tuple)):
            return [
                PermissionSchema.from_string(p) if isinstance(p, str) else p
                for p in value
            ]
        return value


@partial
class APIClientUpdateSchema(APIClientBaseSchema):
    """API Client update schema."""

    is_disabled: pydantic.StrictBool


class APIClientBulkDeleteSchema(pydantic.BaseModel):
    client_uids: typing.Annotated[
        typing.List[pydantic.StrictStr], MinLen(1), MaxLen(50)
    ] = pydantic.Field(
        ...,
        description="List of API Client UIDs to delete",
        min_length=1,
        max_length=50,
    )


__all__ = [
    "APIKeySchema",
    "APIKeyUpdateSchema",
    "APIClientCreateSchema",
    "APIClientSchema",
    "APIClientUpdateSchema",
    "APIClientBulkDeleteSchema",
]

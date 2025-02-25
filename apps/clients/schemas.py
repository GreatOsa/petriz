import pydantic
import typing
from annotated_types import MaxLen, MinLen

from helpers.fastapi.utils import timezone
from helpers.generics.pydantic import partial
from .models import APIClient


class APIKeyBaseSchema(pydantic.BaseModel):
    """API Key base schema."""

    active: pydantic.StrictBool = pydantic.Field(
        description="Is the API Key active and usable?",
        validation_alias="_active",
        serialization_alias="active",
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

    client_type: APIClient.ClientType = pydantic.Field(
        description="API Client type", strip=True
    )


class APIClientSimpleSchema(APIClientBaseSchema):
    """API Client simple schema. For serialization purposes only."""

    uid: pydantic.StrictStr = pydantic.Field(description="API Client UID")
    client_type: APIClient.ClientType = pydantic.Field(
        description="API Client type", strip=True
    )


class APIClientSchema(APIClientBaseSchema):
    """API Client schema. For serialization purposes only."""

    uid: pydantic.StrictStr = pydantic.Field(description="API Client UID")
    client_type: APIClient.ClientType = pydantic.Field(
        description="API Client type", strip=True
    )
    api_key: typing.Optional[APIKeySchema] = pydantic.Field(
        default=None, description="API Key"
    )
    disabled: pydantic.StrictBool = pydantic.Field(
        description="Is the API Client disabled?"
    )
    created_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="API Client creation date and time"
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="API Client last update date and time"
    )

    class Config:
        from_attributes = True


@partial
class APIClientUpdateSchema(APIClientBaseSchema):
    """API Client update schema."""

    disabled: pydantic.StrictBool


class APIClientBulkDeleteSchema(pydantic.BaseModel):
    client_uids: typing.Annotated[
        typing.List[pydantic.StrictStr], MinLen(1), MaxLen(50)
    ] = pydantic.Field(
        ...,
        description="List of API Client UIDs to delete",
    )


__all__ = [
    "APIKeySchema",
    "APIKeyUpdateSchema",
    "APIClientCreateSchema",
    "APIClientSchema",
    "APIClientUpdateSchema",
    "APIClientBulkDeleteSchema",
]

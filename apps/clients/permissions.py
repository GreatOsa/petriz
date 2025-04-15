from enum import Enum
import typing
import pydantic
from pydantic_core._pydantic_core import PydanticCustomError # type: ignore
import re
from typing_extensions import Doc

from .models import APIClient
from helpers.generics.utils.caching import lru_cache


class PermissionScope(Enum):
    """Defines the scope of permissions."""

    GLOBAL = "global"  # Applies to all resources
    RESOURCE = "resource"  # Applies to all instances of resource
    INSTANCE = "instance"  # Applies to single instance of resource


permission_re = re.compile(
    r"^(?P<resource>\w+|\*)?::(?P<instance>\w+|\*)?::(?P<action>\w+|\*)$"
)
"""Regex pattern for permission strings."""
permission_string_template = "{resource}::{instance}::{action}"
"""Expected format for permission strings."""
perm_part_re = re.compile(r"^\w+|\*$")
"""Regex pattern for permission parts."""


@lru_cache
def is_permission_string(permission: str) -> bool:
    """Check if a string is a valid permission string."""
    return bool(permission_re.match(permission))


class PermissionBaseSchema(pydantic.BaseModel):
    """Base schema for permissions."""

    resource: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            pattern=perm_part_re,
        ),
        Doc("The type of resource"),
    ]
    instance: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            pattern=perm_part_re,
        ),
        Doc("The resource identifier"),
    ]
    action: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            to_lower=True,
            min_length=1,
            pattern=perm_part_re,
        ),
        Doc("The permitted action"),
    ]

    def __str__(self) -> str:
        return permission_string_template.format(
            resource=self.resource,
            instance=self.instance,
            action=self.action,
        )

    @pydantic.field_validator("resource", mode="after")
    @classmethod
    def validate_resource(cls, resource: str) -> str:
        if resource != "*" and not resource_exists(resource):
            raise ValueError(f"Unknown resource type '{resource}'")
        return resource

    @pydantic.field_validator("action", mode="after")
    @classmethod
    def validate_action(cls, action: str, info: pydantic.ValidationInfo) -> str:
        if action == "*" or "resource" not in info.data:
            return action

        resource = info.data["resource"]
        if not get_resource_action_data(resource, action):
            raise ValueError(f"Action '{action}' not allowed on resource '{resource}'")
        return action


class PermissionCreateSchema(PermissionBaseSchema):
    """Schema for creating permissions."""

    pass


class PermissionSchema(PermissionBaseSchema):
    """Schema for permissions serialization. Read-only."""

    scope: typing.Annotated[PermissionScope, Doc("The scope of the permission")]
    requires: typing.Annotated[
        typing.Set[
            typing.Annotated[
                str,
                pydantic.StringConstraints(strip_whitespace=True, to_lower=True),
            ]
        ],
        Doc("Other permitted actions this is dependent on"),
    ] = pydantic.Field(default_factory=set)

    def __hash__(self):
        return hash(str(self))

    @classmethod
    def from_string(cls, permission: str):
        """Convert a permission string to a Permission object."""
        try:
            return cls.model_construct(**extract_permission_data(permission))
        except ValueError as exc:
            raise PydanticCustomError("validation_error", str(exc))  # type: ignore

    def to_regex(self) -> re.Pattern:
        """Convert a Permission object to a regex pattern."""
        resource = self.resource if self.resource != "*" else r"\w+|\*"
        instance = self.instance if self.instance != "*" else r"\w+|\*"
        action = self.action if self.action != "*" else r"\w+|\*"
        return re.compile(
            f"^{resource}::{instance}::{action}$".replace("*", r"\w+|\*"),
            flags=re.IGNORECASE,
        )


@lru_cache
def extract_permission_data(permission: str) -> typing.Dict[str, typing.Any]:
    """Extract permission data from a permission string."""
    if not (match := permission_re.match(permission)):
        raise ValueError(
            f"Invalid permission string: {permission}. Format: '{permission_string_template}'"
        )

    resource, instance, action = match.group("resource", "instance", "action")

    # Early return for global permissions
    if resource == "*":
        return {
            "resource": "*",
            "instance": instance,
            "action": action,
            "scope": PermissionScope.GLOBAL,
            "requires": set(),
        }

    if not resource_exists(resource):
        raise ValueError(f"Unknown resource type '{resource}'")

    requires = set()
    if action != "*":
        if not (action_data := get_resource_action_data(resource, action)):
            raise ValueError(
                f"Action '{action!r}' not allowed on resource '{resource}'"
            )

        if action_requires := action_data.get("requires", None):
            requires = {
                req if is_permission_string(req) else f"{resource}::*::{req}"
                for req in action_requires
            }

    return {
        "resource": resource,
        "instance": instance,
        "action": action,
        "scope": PermissionScope.INSTANCE
        if instance != "*"
        else PermissionScope.RESOURCE,
        "requires": requires,
    }


def resource_exists(resource: str) -> bool:
    """Check if a resource exists."""
    return resource in RESOURCES_PERMISSIONS


def get_resource_action_data(
    resource: str, action: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    """Get the data for a specific action on a resource."""
    return RESOURCES_PERMISSIONS[resource].get(action, None)


def resolve_permissions(*permissions: str) -> typing.Set[PermissionSchema]:
    """
    Resolve permissions and their dependencies.

    :param permissions: The permissions to resolve.
    :return: The resolved permissions as a set of `PermissionSchema` objects.
    """
    resolved = set()
    for permission in permissions:
        schema = PermissionSchema.from_string(permission)
        resolved.add(schema)
        dep_schemas = resolve_permissions(*schema.requires)
        resolved.update(dep_schemas)
    return resolved


def check_permissions(client: APIClient, *permissions: PermissionSchema) -> bool:
    """
    Check if an API client has the required permissions.

    :client: The API client to check.
    :permissions: The permissions to check.
    :return: True if the client has the required permissions, False otherwise.
    """
    if not permissions:
        return True
    if not client.permissions:
        return False

    client_patterns = {
        PermissionSchema.from_string(p).to_regex() for p in client.permissions
    }
    return all(
        any(pattern.match(str(permission)) for pattern in client_patterns)
        for permission in permissions
    )


def has_permission(client: APIClient, permission: str) -> bool:
    """Check if a client has a specific permission."""
    return check_permissions(client, PermissionSchema.from_string(permission))


def has_permissions(client: APIClient, *permissions: str) -> bool:
    """Check if a client has the required permissions."""
    return check_permissions(client, *resolve_permissions(*permissions))


@lru_cache
def load_permissions(*permissions: str) -> typing.Set[PermissionSchema]:
    """
    Load permissions from strings.

    :param permissions: The permissions to load.
    :return: The loaded permissions as a set of `PermissionSchema` objects.
    """
    return {PermissionSchema.from_string(permission) for permission in permissions}


PermStr: typing.TypeAlias = str


def validate_permission(
    client: APIClient,
    permission: typing.Union[PermStr, PermissionBaseSchema],
):
    """
    Validate that a permission is allowed for a client.

    :param client: The client to validate.
    :param permission: The permission to validate.
    """
    if isinstance(permission, PermissionBaseSchema):
        permission = str(permission)

    allowed_permission_set = ALLOWED_PERMISSIONS_SETS.get(
        client.client_type.lower(), []
    )
    allowed_permission_set = load_permissions(*allowed_permission_set)

    is_valid = False
    for allowed_permission in allowed_permission_set:
        if allowed_permission.to_regex().match(permission):
            is_valid = True
            break

    if not is_valid:
        raise ValueError(
            f"Permission '{permission}' not allowed for {client.client_type.lower()!r} type clients"
        )
    return


def validate_permissions(
    client: APIClient,
    *permissions: typing.Union[str, PermissionBaseSchema],
):
    """
    Validate that the given permissions are allowed for a client.

    :param client: The client to validate.
    :param permissions: The permissions to validate.
    """
    for permission in permissions:
        validate_permission(client, permission)
    return


DEFAULT_ACTIONS = {
    "list": {
        "description": "List all resources_PERMISSIONS",
        "requires": None,
    },
    "view": {
        "description": "Retrieve a single resource",
        "requires": {"list"},
    },
    "create": {
        "description": "Create a new resource",
        "requires": None,
    },
    "update": {
        "description": "Update an existing resource",
        "requires": {"view"},
    },
    "delete": {
        "description": "Delete an existing resource",
        "requires": {"view"},
    },
}


RESOURCES_PERMISSIONS = {
    "accounts": {
        **DEFAULT_ACTIONS,
        "authenticate": {
            "description": "Authenticate users",
            "requires": {"view", "update"},
        },
    },
    "api_clients": {
        **DEFAULT_ACTIONS,
        "permissions_update": {
            "description": "Update API clients permissions",
            "requires": {"update"},
        },
    },
    "api_keys": {
        "view": {
            "description": "Retrieve API keys",
            "requires": {"api_clients::*::view"},
        },
        "update": {
            "description": "Update API keys",
            "requires": {"api_clients::*::view"},
        },
    },
    "terms": DEFAULT_ACTIONS,
    "topics": DEFAULT_ACTIONS,
    "term_sources": DEFAULT_ACTIONS,
    "search_records": {
        "list": {
            "description": "List all search records",
            "requires": None,
        },
        "list_own": {
            "description": "List own search records",
            "requires": {"list"},
        },
        "create": {
            "description": "Create search records",
            "requires": None,
        },
        "delete": {
            "description": "Delete search records",
            "requires": None,
        },
    },
    "questions": {
        **DEFAULT_ACTIONS,
        "attempt": {
            "description": "Attempt a question",
            "requires": {"update"},
        },
    },
    "quizzes": {
        **DEFAULT_ACTIONS,
        "create": {
            "description": "Create a new quiz",
            "requires": {"update", "questions::*::create"},
        },
        "attempt": {
            "description": "Attempt a quiz",
            "requires": {"update", "questions::*::attempt"},
        },
    },
    "audit_log_entries": {
        "list": {
            "description": "List all audit log entries",
            "requires": None,
        },
    },
}


ALLOWED_PERMISSIONS_SETS = {
    "internal": {
        "*::*::*",  # All access
    },
    "public": {
        "terms::*::list",
        "terms::*::view",
        "topics::*::list",
        "topics::*::view",
        "term_sources::*::list",
        "term_sources::*::view",
        "search_records::*::create",
        "quizzes::*::list",
        "quizzes::*::view",
        "quizzes::*::attempt",
        "questions::*::list",
        "questions::*::attempt",
    },
    "partner": {
        "accounts::*::*",
        "api_clients::*::*",
        "api_keys::*::*",
        "terms::*::*",
        "topics::*::*",
        "term_sources::*::*",
        "search_records::*::*",
        "quizzes::*::*",
        "questions::*::*",
    },
    "user": {
        "api_clients::*::*",
        "api_keys::*::*",
        "terms::*::list",
        "terms::*::view",
        "topics::*::list",
        "topics::*::view",
        "search_records::*::list",
        "search_records::*::list_own",
        "search_records::*::delete",
        "search_records::*::create",
        "quizzes::*::list",
        "quizzes::*::view",
        "quizzes::*::create",
        "quizzes::*::update",
        "quizzes::*::delete",
        "quizzes::*::attempt",
        "questions::*::list",
        "questions::*::create",
        "questions::*::update",
        "questions::*::attempt",
    },
}

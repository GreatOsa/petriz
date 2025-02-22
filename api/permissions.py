from enum import Enum
import typing
import pydantic
import re
from typing_extensions import Doc

from apps.clients.models import APIClient


class PermissionScope(Enum):
    """Defines the scope of permissions."""

    GLOBAL = "global"  # Applies to all resources
    RESOURCE = "resource"  # Applies to all instances of resource
    INSTANCE = "instance"  # Applies to single instance of resource


permission_re = re.compile(
    r"^(?P<resource>\w+|\*)?::(?P<instance>\w+|\*)?::(?P<action>\w+)$"
)
permission_string_template = "{resource}::{instance}::{action}"


def is_permission_string(permission: str) -> bool:
    return bool(permission_re.match(permission))


class PermissionBaseSchema(pydantic.BaseModel):
    """Base schema for permissions."""

    resource: typing.Annotated[typing.Optional[str], Doc("The type of resource")]
    instance: typing.Annotated[typing.Optional[str], Doc("The resource identifier")]
    action: typing.Annotated[
        typing.Optional[str],
        pydantic.StringConstraints(strip_whitespace=True, to_lower=True),
        Doc("The permitted action"),
    ]


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

    def __str__(self):
        if self.scope == PermissionScope.GLOBAL:
            return permission_string_template.format(
                resource="*",
                instance="*",
                action=self.action or "*",
            )
        return permission_string_template.format(
            resource=self.resource or "*",
            instance=self.instance or "*",
            action=self.action or "*",
        )

    def __hash__(self):
        return hash(str(self))

    @classmethod
    def from_string(cls, permission: str):
        """Convert a permission string to a Permission object."""
        return cls(**extract_permission_data(permission))

    def to_regex(self) -> re.Pattern:
        """Convert a Permission object to a regex pattern."""
        resource = self.resource or r"\w+"
        instance = self.instance or r"\w+"
        action = self.action
        return re.compile(f"^{resource}::{instance}::{action}$")


def extract_permission_data(permission: str) -> typing.Tuple[str, str, str]:
    match = permission_re.match(permission)
    if not match:
        raise ValueError(f"Invalid permission string: {permission}")

    resource = match.group("resource")
    instance = match.group("instance")
    action = match.group("action")
    if not action:
        raise ValueError(f"Invalid permission string: {permission!r}")

    if resource == "*":
        resource = None
    if instance == "*":
        instance = None

    scope = PermissionScope.GLOBAL
    requires: typing.Set[str] = set()
    if resource:
        if not resource_exists(resource):
            raise ValueError(f"Unknown resource type '{resource!r}'")

        action_data = get_resource_action_data(resource, action)
        if not action_data:
            raise ValueError(f"Action '{action!r}' not allowed on resource '{resource!r}'")

        # Format required permissions as proper permission strings
        # where necessary
        action_requires = set(action_data.get("requires", None) or [])
        for requirement in action_requires:
            if is_permission_string(requirement):
                requires.add(requirement)
            else:
                requires.add(
                    permission_string_template.format(
                        resource=resource, instance="*", action=requirement
                    )
                )

        if instance:
            scope = PermissionScope.INSTANCE
        else:
            scope = PermissionScope.RESOURCE
    return {
        "resource": resource,
        "instance": instance,
        "action": action,
        "scope": scope,
        "requires": requires,
    }


def resource_exists(resource: str) -> bool:
    return resource in RESOURCES


def get_resource_action_data(
    resource: str, action: str
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    return RESOURCES[resource].get(action, None)


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
    """Check if a client has the required permissions."""
    if not permissions:
        return True
    if not client.permissions:
        return False

    for permission in permissions:
        if not any(permission.to_regex().match(p) for p in set(client.permissions)):
            return False
    return True


DEFAULT_ACTIONS = {
    "list": {
        "description": "List all resources",
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
        "requires": {"retrieve"},
    },
    "delete": {
        "description": "Delete an existing resource",
        "requires": {"retrieve"},
    },
}


RESOURCES = {
    "terms": DEFAULT_ACTIONS,
    "topics": DEFAULT_ACTIONS,
    "clients": DEFAULT_ACTIONS,
    "search": {
        "list": {
            "description": "List search results",
            "requires": None,
        },
    },
    "search_history": {
        "list": {
            "description": "List search history",
            "requires": None,
        },
        "delete": {
            "description": "Delete search history",
            "requires": None,
        },
    },
}

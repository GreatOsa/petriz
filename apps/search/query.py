import typing
import fastapi
import pydantic
import datetime

from helpers.fastapi.utils import timezone


SearchQuery = typing.Annotated[
    typing.Optional[str], fastapi.Query(description="Search query", max_length=255)
]
"""Annotated dependency for a search query parameter of not more than 255 characters"""


def parse_topics_query(
    topics: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Comma-separated string of topics to filter by",
        ),
    ] = None,
) -> typing.Optional[typing.List[str]]:
    if not topics:
        return None
    return list({topic.strip() for topic in topics.split(",")})


def parse_startswith_query(
    startswith: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Filter terms that start with a specific letter or letters",
        ),
    ] = None,
) -> typing.Optional[str]:
    if not startswith:
        return None
    return list({letter.strip() for letter in startswith.split(",")})


def parse_verified_query(
    verified: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Whether to only include terminologies that have been vetted and verified to be correct",
        ),
    ] = None,
) -> typing.Optional[bool]:
    if not verified:
        return None
    return pydantic.TypeAdapter(bool).validate_python(verified, strict=False)


Topics = typing.Annotated[
    typing.Optional[typing.List[str]], fastapi.Depends(parse_topics_query)
]
"""
Annotated dependency to parse topics query parameter into a list of strings
"""

Startswith = typing.Annotated[
    typing.Optional[str], fastapi.Depends(parse_startswith_query)
]
"""
Annotated dependency to parse startswith query parameter into list of strings
"""

Verified = typing.Annotated[
    typing.Optional[bool],
    fastapi.Depends(parse_verified_query),
]
"""
Annotated dependency to parse verified query parameter into a boolean
"""


def timestamp_query_parser(query_param: str):
    """
    Factory function to create a dependency that parses a timestamp query parameter
    into a (tiezone-aware) datetime object

    :param query_param: The name of the query parameter to parse
    :return: A dependency function that parses the query parameter into a datetime object
    """

    def _query_parser(
        timestamp: typing.Annotated[
            typing.Optional[str],
            fastapi.Query(
                description="String representing a datetime",
                alias=query_param,
                alias_priority=1,
            ),
        ] = None,
    ) -> typing.Optional[datetime.datetime]:
        if not timestamp:
            return None
        return (
            pydantic.TypeAdapter(pydantic.AwareDatetime)
            .validate_python(timestamp, strict=False)
            .astimezone(timezone.get_current_timezone())
        )

    _query_parser.__name__ = f"parse_{query_param}_query"
    return _query_parser


TimestampGte = typing.Annotated[
    typing.Optional[datetime.datetime],
    fastapi.Depends(timestamp_query_parser("timestamp_gte")),
]
"""Annotated dependency to parse timestamp_gte query parameter into a timezone-aware datetime"""

TimestampLte = typing.Annotated[
    typing.Optional[datetime.datetime],
    fastapi.Depends(timestamp_query_parser("timestamp_lte")),
]
"""Annotated dependency to parse timestamp_lte query parameter into a timezone-aware datetime"""


__all__ = [
    "Topics",
    "Startswith",
    "Verified",
    "SearchQuery",
    "TimestampGte",
    "TimestampLte",
]

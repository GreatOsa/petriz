import typing
import fastapi
import pydantic
import datetime

from helpers.fastapi.utils import timezone
from helpers.fastapi.requests.query import (
    QueryParamNotSet,
    ParamNotSet,
    OrderingExpressions,
    ordering_query_parser_factory,
)

from .models import Term


def parse_query(
    query: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(description="Search query", max_length=255),
    ] = None,
) -> typing.Union[str, QueryParamNotSet]:
    """Parse a search query parameter"""
    if query is None:
        return ParamNotSet
    return query.strip() or ParamNotSet


SearchQuery: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet], fastapi.Depends(parse_query)
]
"""Annotated type for a search query parameter of not more than 255 characters"""


def parse_source_query(
    source: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Name or UID of preferred source of query results",
            max_length=255,
        ),
    ] = None,
) -> typing.Union[str, QueryParamNotSet]:
    if source is None:
        return ParamNotSet
    return source.strip() or ParamNotSet


Source: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(parse_source_query),
]
"""Annotated type for a query result's source name or UID of not more than 255 characters"""


def parse_topics_query(
    topics: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Comma-separated string of topic names or UIDs to filter by",
        ),
    ] = None,
) -> typing.Union[typing.List[str], QueryParamNotSet]:
    if topics is None:
        return ParamNotSet
    return list({topic.strip() for topic in topics.split(",") if topic.strip()})


def parse_startswith_query(
    startswith: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Filter terms that start with a specific letter or letters",
        ),
    ] = None,
) -> typing.Union[typing.List[str], QueryParamNotSet]:
    if startswith is None:
        return ParamNotSet
    return list({letter.strip() for letter in startswith.split(",")})


def parse_verified_query(
    verified: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Whether to only include terminologies that have been vetted and verified to be correct",
        ),
    ] = None,
) -> typing.Union[bool, QueryParamNotSet]:
    if verified is None:
        return ParamNotSet
    return pydantic.TypeAdapter(bool).validate_python(verified, strict=False)


Topics: typing.TypeAlias = typing.Annotated[
    typing.Union[typing.List[str], QueryParamNotSet],
    fastapi.Depends(parse_topics_query),
]
"""
Annotated dependency to parse topics query parameter into a list of strings
"""

Startswith: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet],
    fastapi.Depends(parse_startswith_query),
]
"""
Annotated dependency to parse `startswith` query parameter into list of strings
"""

Verified: typing.TypeAlias = typing.Annotated[
    typing.Union[bool, QueryParamNotSet],
    fastapi.Depends(parse_verified_query),
]
"""
Annotated dependency to parse `verified` query parameter into a boolean
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
    ) -> typing.Union[datetime.datetime, QueryParamNotSet]:
        if timestamp is None:
            return ParamNotSet
        return (
            pydantic.TypeAdapter(pydantic.AwareDatetime)
            .validate_python(timestamp, strict=False)
            .astimezone(timezone.get_current_timezone())
        )

    _query_parser.__name__ = f"parse_{query_param}_query"
    return _query_parser


TimestampGte: typing.TypeAlias = typing.Annotated[
    typing.Union[datetime.datetime, QueryParamNotSet],
    fastapi.Depends(timestamp_query_parser("timestamp_gte")),
]
"""Annotated dependency to parse `timestamp_gte` query parameter into a timezone-aware datetime"""

TimestampLte: typing.TypeAlias = typing.Annotated[
    typing.Union[datetime.datetime, QueryParamNotSet],
    fastapi.Depends(timestamp_query_parser("timestamp_lte")),
]
"""Annotated dependency to parse `timestamp_lte` query parameter into a timezone-aware datetime"""

terms_ordering_query_parser = ordering_query_parser_factory(
    Term,
    allowed_columns={
        "name",
        "verified",
    },
)

TermsOrdering: typing.TypeAlias = typing.Annotated[
    typing.Union[OrderingExpressions[Term], QueryParamNotSet],
    fastapi.Depends(terms_ordering_query_parser),
]

__all__ = [
    "Topics",
    "Startswith",
    "Verified",
    "SearchQuery",
    "TimestampGte",
    "TimestampLte",
    "TermsOrdering",
]

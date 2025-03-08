import typing
import fastapi

from helpers.fastapi.requests.query import (
    QueryParamNotSet,
    OrderingExpressions,
    ordering_query_parser_factory,
)

from .models import APIClient


clients_ordering_query_parser = ordering_query_parser_factory(
    APIClient,
    allowed_columns=[
        "name",
        "client_type",
        "created_at",
        "updated_at",
    ],
)

APIClientOrdering: typing.TypeAlias = typing.Annotated[
    typing.Union[OrderingExpressions[APIClient], QueryParamNotSet],
    fastapi.Depends(clients_ordering_query_parser),
]

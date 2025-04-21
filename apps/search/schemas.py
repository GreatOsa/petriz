import typing
from annotated_types import MaxLen, MinLen
import pydantic

from helpers.generics.pydantic import partial
from apps.clients.schemas import APIClientSimpleSchema


class TopicBaseSchema(pydantic.BaseModel):
    """Topic base schema."""

    name: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=1000,
        ),
    ] = pydantic.Field(
        ...,
        description="The name of the topic",
    )
    description: typing.Annotated[
        typing.Optional[str],
        MaxLen(5000),
        MinLen(1),
    ] = pydantic.Field(
        ...,
        description="What aspects does the topic cover?",
    )

    def __hash__(self):
        return hash(self.name)


class TopicCreateSchema(TopicBaseSchema):
    """Topic creation schema."""

    pass


@partial
class TopicUpdateSchema(TopicBaseSchema):
    """Topic update schema."""

    pass


class TopicSchema(TopicBaseSchema):
    """Topic schema. For serialization purposes only."""

    uid: pydantic.StrictStr
    created_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the topic was created/added"
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the topic was last updated"
    )

    class Config:
        from_attributes = True


class TermSourceBaseSchema(pydantic.BaseModel):
    """TermSource base schema."""

    name: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=255,
        ),
    ] = pydantic.Field(
        ...,
        description="The name of the source",
    )
    url: typing.Optional[pydantic.AnyUrl] = pydantic.Field(
        None, description="The URL of the source", max_length=500
    )
    description: typing.Annotated[
        typing.Optional[str],
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=5000,
        ),
    ] = pydantic.Field(
        None,
        description="Description of the source",
    )


class TermSourceCreateSchema(TermSourceBaseSchema):
    """TermSource creation schema."""

    pass


@partial
class TermSourceGetOrCreateSchema(TermSourceBaseSchema):
    """TermSource get or create schema."""

    uid: typing.Optional[pydantic.StrictStr] = pydantic.Field(
        None,
        description="The UID of the source",
    )


@partial
class TermSourceUpdateSchema(TermSourceBaseSchema):
    """TermSource update schema."""

    pass


class TermSourceSchema(TermSourceBaseSchema):
    """TermSource schema. For serialization purposes only."""

    uid: pydantic.StrictStr
    created_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the source was created/added"
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the source was last updated"
    )

    class Config:
        from_attributes = True


class TermBaseSchema(pydantic.BaseModel):
    """Term base schema."""

    name: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=500,
        ),
    ] = pydantic.Field(
        ...,
        description="The name of the term",
    )
    definition: typing.Annotated[
        str,
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=5000,
        ),
    ] = pydantic.Field(
        ...,
        description="The definition of the term",
    )
    grammatical_label: typing.Annotated[
        typing.Optional[pydantic.StrictStr],
        pydantic.StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=50,
        ),
    ] = pydantic.Field(
        None,
        description="The part of speech of the term",
    )


class TermCreateSchema(TermBaseSchema):
    """Term creation schema."""

    source: typing.Optional[TermSourceGetOrCreateSchema] = pydantic.Field(
        None,
        description="The source from which the term was obtained, by name or UID",
    )
    topics: typing.Set[str] = pydantic.Field(
        default_factory=set,
        description="The topics the term belongs to, by name or UID",
    )


@partial
class TermUpdateSchema(TermBaseSchema):
    """Term update schema."""

    source: typing.Optional[TermSourceGetOrCreateSchema] = pydantic.Field(
        None,
        description="The source from which the term was obtained, by name or UID",
    )
    verified: pydantic.StrictBool = pydantic.Field(
        description="Whether the term an its definition have been vetted and verified to be correct",
    )
    topics: typing.Set[str] = pydantic.Field(
        default_factory=set,
        description="The topics the term belongs to, by name or UID",
    )
    replace_topics: pydantic.StrictBool = pydantic.Field(
        False,
        description="Whether to replace the existing topics with the new ones. If False, the new topics will be added to the existing ones",
    )


class BaseTermSchema(TermBaseSchema):
    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        ...,
        description="The UID of the term",
    )
    verified: pydantic.StrictBool = pydantic.Field(
        False,
        description="Whether the term an its definition have been vetted and verified to be correct",
    )
    created_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the term was created/added"
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the term was last updated"
    )

    class Config:
        from_attributes = True

    def __hash__(self):
        return hash(self.uid)


class TermSchema(BaseTermSchema):
    """Term schema. For serialization purposes only."""

    source: typing.Optional[TermSourceSchema] = pydantic.Field(
        None,
        description="The source from which the term was obtained",
    )
    topics: typing.Set[TopicSchema] = pydantic.Field(
        default_factory=set,
        description="The topics the term belongs to",
    )
    related: typing.Set[BaseTermSchema] = pydantic.Field(
        alias="relatives",
        default_factory=set,
        description="The terms related to this term",
    )


class SearchRecordSchema(pydantic.BaseModel):
    """SearchRecord schema. For serialization purposes only."""

    uid: pydantic.StrictStr
    query: typing.Annotated[
        typing.Optional[str],
        pydantic.StringConstraints(
            strip_whitespace=True,
            max_length=255,
        ),
    ] = pydantic.Field(
        default=None,
        description="The search query made",
    )
    topics: typing.Set[TopicSchema] = pydantic.Field(
        default_factory=set,
        description="The topics the search query was made on",
    )
    client: typing.Optional[APIClientSimpleSchema] = pydantic.Field(
        description="The client that made the search"
    )
    metadata: typing.Optional[typing.Dict[str, pydantic.JsonValue]] = pydantic.Field(
        default=None,
        description="Extra data associated with the search",
        validation_alias=pydantic.AliasChoices(
            "extradata",
            "metadata",
        ),
        serialization_alias="metadata",
        alias_priority=1,
    )
    timestamp: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="The date and time the search was made"
    )

    class Config:
        from_attributes = True


class AccountSearchMetricsSchema(pydantic.BaseModel):
    """Account search metrics schema. For serialization purposes only."""

    account_id: pydantic.StrictStr
    search_count: pydantic.PositiveInt = pydantic.Field(
        default=0,
        description="The total number of searches made by the account, over a period of time",
    )
    most_searched_queries: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = (
        pydantic.Field(
            default_factory=dict,
            description="Mapping of the most searched queries by the account to the number of times they were searched",
        )
    )
    most_searched_topics: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = (
        pydantic.Field(
            default_factory=dict,
            description="Mapping of the most searched topics by the account to the number of account queries made on them",
        )
    )
    most_searched_words: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = (
        pydantic.Field(
            default_factory=dict,
            description="Mapping of the most searched words by the account to the number of account queries made with them",
        )
    )
    period_start: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="The start of the period the metrics were calculated for",
    )
    period_end: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="The end of the period the metrics were calculated for",
    )


class GlobalSearchMetricsSchema(pydantic.BaseModel):
    """Global search metrics schema. For serialization purposes only."""

    search_count: pydantic.PositiveInt = pydantic.Field(
        default=0,
        description="The total number of searches made by users, over a period of time",
    )
    verified_term_count: pydantic.PositiveInt = pydantic.Field(
        default=0,
        description="The total number of verified terms in the glossary",
    )
    unverified_term_count: pydantic.PositiveInt = pydantic.Field(
        default=0,
        description="The total number of unverified terms in the glossary",
    )
    sources: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = pydantic.Field(
        default_factory=dict,
        description="Mapping of the sources of terms in the glossary to the number of terms from each source",
    )
    most_searched_queries: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = (
        pydantic.Field(
            default_factory=dict,
            description="Mapping of the most searched queries by users to the number of times they were searched",
        )
    )
    most_searched_topics: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = (
        pydantic.Field(
            default_factory=dict,
            description="Mapping of the most searched topics by users to the number of queries made on them",
        )
    )
    most_searched_words: typing.Optional[typing.Dict[pydantic.StrictStr, int]] = (
        pydantic.Field(
            default_factory=dict,
            description="Mapping of the most searched words by users to the number of queries made with them",
        )
    )
    period_start: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="The start of the period the metrics were calculated for",
    )
    period_end: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="The end of the period the metrics were calculated for",
    )


__all__ = [
    "TermCreateSchema",
    "TermUpdateSchema",
    "TermSchema",
    "SearchRecordSchema",
    "AccountSearchMetricsSchema",
    "GlobalSearchMetricsSchema",
]

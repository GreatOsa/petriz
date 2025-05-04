import typing
import fastapi
import pydantic
import datetime
from typing_extensions import Doc

from helpers.fastapi.requests.query import (
    QueryParamNotSet,
    ParamNotSet,
    OrderingExpressions,
    ordering_query_parser_factory,
    timestamp_query_parser,
)
from helpers.generics.pydantic import BoolLike


from .models import (
    Question,
    Quiz,
    QuestionDifficulty as QuestionDifficultyEnum,
    QuizAttempt,
    QuizDifficulty as QuizDifficultyEnum,
)


async def parse_query(
    query: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Search for quizzes with this query",
            title="Search query",
            max_length=255,
        ),
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


async def parse_quiz_title(
    title: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            title="Quiz title",
            description="Only quizzes with titles containing this value will be returned",
            max_length=255,
        ),
    ] = None,
) -> typing.Union[str, QueryParamNotSet]:
    """Parse quiz title query parameter"""
    if title is None:
        return ParamNotSet
    return title.strip() or ParamNotSet


QuizTitle: typing.TypeAlias = typing.Annotated[
    typing.Union[str, QueryParamNotSet], fastapi.Depends(parse_quiz_title)
]
"""Annotated type for a quiz title query parameter of not more than 255 characters"""

quiz_difficulty_levels = [
    member.value for member in QuestionDifficultyEnum.__members__.values()
]


async def parse_quiz_difficulty(
    difficulty: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Provide a comma-separated list of quiz difficulty levels",
            title="Quiz difficulty levels",
            max_length=20,
            examples=[
                *quiz_difficulty_levels,
                ",".join(quiz_difficulty_levels[:-1]),
            ],
        ),
    ] = None,
) -> typing.Union[typing.List[str], QueryParamNotSet]:
    """Parse quiz difficulty query parameter"""
    if difficulty is None:
        return ParamNotSet

    difficulty_levels = difficulty.strip().lower().split(",")
    for level in difficulty_levels:
        if level not in quiz_difficulty_levels:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid difficulty level: {level}. Allowed levels are: {', '.join(quiz_difficulty_levels)}",
            )
    if not difficulty_levels:
        return ParamNotSet
    return list(set(difficulty_levels))


question_difficulty_levels = [
    member.value for member in QuestionDifficultyEnum.__members__.values()
]


async def parse_question_difficulty(
    difficulty: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Provide a comma-separated list of question difficulty levels",
            title="Question difficulty levels",
            max_length=20,
            examples=[
                *question_difficulty_levels,
                ",".join(question_difficulty_levels[:-1]),
            ],
        ),
    ] = None,
) -> typing.Union[typing.List[str], QueryParamNotSet]:
    """Parse question difficulty query parameter"""
    if difficulty is None:
        return ParamNotSet

    difficulty_levels = difficulty.strip().lower().split(",")
    for level in difficulty_levels:
        if level not in question_difficulty_levels:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid difficulty level: {level}. Allowed levels are: {', '.join(question_difficulty_levels)}",
            )
    if not difficulty_levels:
        return ParamNotSet
    return list(set(difficulty_levels))


async def parse_quiz_duration_gte(
    duration_gte: typing.Annotated[
        typing.Optional[pydantic.PositiveFloat],
        fastapi.Query(
            description="Only quizzes with a duration greater than or equal to this value will be returned",
            ge=1,
            example=10,
        ),
    ] = None,
) -> typing.Union[float, QueryParamNotSet]:
    """Parse quiz duration query parameter"""
    if duration_gte is None:
        return ParamNotSet
    return duration_gte


async def parse_quiz_duration_lte(
    duration_lte: typing.Annotated[
        typing.Optional[pydantic.PositiveFloat],
        fastapi.Query(
            description="Only quizzes with a duration less than or equal to this value will be returned",
            ge=1,
            example=10,
        ),
    ] = None,
) -> typing.Union[float, QueryParamNotSet]:
    """Parse quiz duration query parameter"""
    if duration_lte is None:
        return ParamNotSet
    return duration_lte


async def parse_is_public(
    is_public: typing.Annotated[
        typing.Optional[BoolLike],
        fastapi.Query(description="Should only public quizzes be returned?"),
    ] = None,
) -> typing.Union[bool, QueryParamNotSet]:
    """Parse is_public query parameter"""
    if is_public is None:
        return ParamNotSet
    return is_public


async def parse_private_only(
    private_only: typing.Annotated[
        typing.Optional[BoolLike],
        fastapi.Query(
            description="Should only quizzes created by the authenticated user be returned?"
        ),
    ] = None,
) -> typing.Union[bool, QueryParamNotSet]:
    """Parse private_only query parameter"""
    if private_only is None:
        return ParamNotSet
    return private_only


def parse_quiz_uids(
    quiz_uids: typing.Annotated[
        typing.Optional[str],
        fastapi.Query(
            description="Comma-separated string of quiz UIDs to filter by",
        ),
    ] = None,
) -> typing.Union[typing.List[str], QueryParamNotSet]:
    if quiz_uids is None:
        return ParamNotSet
    return list({uid.strip() for uid in quiz_uids.split(",") if uid.strip()})


QuizDifficulty: typing.TypeAlias = typing.Annotated[
    typing.Union[QuizDifficultyEnum, QueryParamNotSet],
    fastapi.Depends(parse_quiz_difficulty),
]
"""Annotated type for a quiz difficulty query parameter"""

QuestionDifficulty: typing.TypeAlias = typing.Annotated[
    typing.Union[QuestionDifficultyEnum, QueryParamNotSet],
    fastapi.Depends(parse_question_difficulty),
]
"""Annotated type for a question difficulty query parameter"""

QuizDurationGte: typing.TypeAlias = typing.Annotated[
    typing.Union[float, QueryParamNotSet],
    fastapi.Depends(parse_quiz_duration_gte),
]
"""Annotated type for a quiz duration_gte query parameter"""

QuizDurationLte: typing.TypeAlias = typing.Annotated[
    typing.Union[float, QueryParamNotSet],
    fastapi.Depends(parse_quiz_duration_lte),
]
"""Annotated type for a quiz duration_lte query parameter"""

QuizIsPublic: typing.TypeAlias = typing.Annotated[
    typing.Union[bool, QueryParamNotSet],
    fastapi.Depends(parse_is_public),
]
"""Annotated type for a quiz is_public query parameter"""

OnlyPrivateQuizzes = typing.Annotated[
    typing.Union[bool, QueryParamNotSet],
    fastapi.Depends(parse_private_only),
]
"""Annotated type for a quiz private_only query parameter"""

CreatedAtGte: typing.TypeAlias = typing.Annotated[
    typing.Union[
        datetime.datetime,
        QueryParamNotSet,
    ],
    fastapi.Depends(
        timestamp_query_parser(
            "created_at_gte",
        ),
    ),
]
"""Annotated type for a created_at_gte query parameter"""

CreatedAtLte: typing.TypeAlias = typing.Annotated[
    typing.Union[
        datetime.datetime,
        QueryParamNotSet,
    ],
    fastapi.Depends(
        timestamp_query_parser(
            "created_at_lte",
        ),
    ),
]
"""Annotated type for a created_at_lte query parameter"""

UpdatedAtGte: typing.TypeAlias = typing.Annotated[
    typing.Union[
        datetime.datetime,
        QueryParamNotSet,
    ],
    fastapi.Depends(
        timestamp_query_parser(
            "updated_at_gte",
        ),
    ),
]
"""Annotated type for a updated_at_gte query parameter"""

UpdatedAtLte: typing.TypeAlias = typing.Annotated[
    typing.Union[
        datetime.datetime,
        QueryParamNotSet,
    ],
    fastapi.Depends(
        timestamp_query_parser(
            "updated_at_lte",
        ),
    ),
]
"""Annotated type for a updated_at_lte query parameter"""

QuizUIDs: typing.TypeAlias = typing.Annotated[
    typing.Union[typing.List[str], QueryParamNotSet],
    fastapi.Depends(parse_quiz_uids),
]
"""Annotated type for a quiz UIDs query parameter"""

Version: typing.TypeAlias = typing.Annotated[
    typing.Optional[int],
    fastapi.Query(
        ge=0,
        le=100,
    ),
]

QuizVersion: typing.TypeAlias = typing.Annotated[
    Version,
    Doc("Quiz version Leave blank for latest."),
]
QuestionVersion: typing.TypeAlias = typing.Annotated[
    Version, Doc("Quiz version. Leave blank for latest.")
]

quiz_ordering_query_parser = ordering_query_parser_factory(
    Quiz,
    allowed_columns={
        "title",
        "difficulty",
        "duration",
        "version",
        "questions_count",
        "is_public",
        "created_at",
        "updated_at",
    },
)

question_ordering_query_parser = ordering_query_parser_factory(
    Question,
    allowed_columns={
        "difficulty",
        "version",
        "created_at",
        "updated_at",
    },
)

quiz_attempt_ordering_query_parser = ordering_query_parser_factory(
    QuizAttempt,
    allowed_columns={
        "duration",
        "score",
        "is_submitted",
        "submitted_at",
        "created_at",
        "updated_at",
    },
)

QuizOrdering: typing.TypeAlias = typing.Annotated[
    typing.Union[OrderingExpressions[Quiz], QueryParamNotSet],
    fastapi.Depends(quiz_ordering_query_parser),
]
"""Annotated type for a quiz ordering query parameter"""

QuestionOrdering: typing.TypeAlias = typing.Annotated[
    typing.Union[OrderingExpressions[Question], QueryParamNotSet],
    fastapi.Depends(question_ordering_query_parser),
]
"""Annotated type for a question ordering query parameter"""

QuizAttemptOrdering: typing.TypeAlias = typing.Annotated[
    typing.Union[OrderingExpressions[QuizAttempt], QueryParamNotSet],
    fastapi.Depends(quiz_attempt_ordering_query_parser),
]
"""Annotated type for a quiz attempt ordering query parameter"""

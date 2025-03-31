import typing
import pydantic
from annotated_types import Interval, MaxLen

from helpers.generics.pydantic import partial
from apps.quizzes.models import QuestionDifficulty, QuizDifficulty
from apps.search.schemas import BaseTermSchema, TopicSchema
from apps.accounts.schemas import BaseAccountSchema


class QuestionBaseSchema(pydantic.BaseModel):
    """Question base schema."""

    question: typing.Optional[
        typing.Annotated[
            pydantic.StrictStr,
            pydantic.StringConstraints(
                strip_whitespace=True,
                to_lower=True,
                min_length=6,
                max_length=5000,
            ),
        ]
    ] = pydantic.Field(
        description="Question text",
    )
    description: typing.Optional[pydantic.StrictStr] = pydantic.Field(
        default=None, max_length=500, description="Question description"
    )
    options: typing.List[
        typing.Annotated[
            pydantic.StrictStr,
            pydantic.StringConstraints(
                strip_whitespace=True,
                to_lower=True,
                min_length=1,
                max_length=500,
            ),
        ]
    ] = pydantic.Field(description="Question options", max_length=6)
    correct_option_index: typing.Annotated[
        pydantic.StrictInt,
        Interval(ge=0, le=5),
    ] = pydantic.Field(
        description="Index of the correct option",
    )
    difficulty: QuestionDifficulty = pydantic.Field(
        QuestionDifficulty.NOT_SET,
        description="Question difficulty",
    )
    hint: typing.Optional[pydantic.StrictStr] = pydantic.Field(
        default=None, max_length=2000, description="Question hint"
    )


class QuestionCreateSchema(QuestionBaseSchema):
    """Question create schema."""

    pass


@partial
class QuestionUpdateSchema(QuestionBaseSchema):
    """Question update schema."""

    pass


class BaseQuestionSchema(QuestionBaseSchema):
    """Base Question schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Question unique identifier",
    )
    created_at: pydantic.AwareDatetime = pydantic.Field(
        description="Question creation datetime",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Question update datetime",
    )

    class Config:
        from_attributes = True

    def __hash__(self) -> int:
        return hash(self.uid)


class QuestionSchema(BaseQuestionSchema):
    """Question schema. For serialization purposes only."""

    related_terms: typing.Set[BaseTermSchema] = pydantic.Field(
        description="Terms related to the question",
    )
    related_topics: typing.Set[TopicSchema] = pydantic.Field(
        description="Topics related to the question",
    )


class QuizBaseSchema(pydantic.BaseModel):
    """Quiz base schema."""

    title: typing.Optional[
        typing.Annotated[
            pydantic.StrictStr,
            pydantic.StringConstraints(
                strip_whitespace=True,
                to_lower=True,
                min_length=6,
                max_length=100,
            ),
        ]
    ] = pydantic.Field(
        description="Quiz title",
    )
    description: typing.Optional[pydantic.StrictStr] = pydantic.Field(
        default=None, max_length=500, description="Quiz description"
    )
    difficulty: QuizDifficulty = pydantic.Field(
        QuizDifficulty.NOT_SET, description="Quiz difficulty"
    )
    duration: typing.Optional[pydantic.StrictInt] = pydantic.Field(
        default=None,
        description="Quiz duration in minutes",
    )
    is_public: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Is the quiz public",
    )
    metadata: typing.Dict[pydantic.StrictStr, pydantic.JsonValue] = pydantic.Field(
        alias="data",
        default={},
        description="Quiz metadata",
        union_mode="smart",
    )


class QuizCreateSchema(QuizBaseSchema):
    """Quiz create schema."""

    questions: typing.List[BaseQuestionSchema] = pydantic.Field(
        description="Quiz questions",
    )


@partial
class QuizUpdateSchema(QuizCreateSchema):
    """Quiz update schema."""

    pass


class BaseQuizSchema(QuizBaseSchema):
    """Base Quiz schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Quiz unique identifier",
    )
    created_at: pydantic.AwareDatetime = pydantic.Field(
        description="Quiz creation datetime",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Quiz update datetime",
    )

    class Config:
        from_attributes = True

    def __hash__(self) -> int:
        return hash(self.uid)


class QuizSchema(BaseQuizSchema):
    """Quiz schema. For serialization purposes only."""

    questions: typing.List[BaseQuestionSchema] = pydantic.Field(
        description="Quiz questions",
    )
    created_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        description="Quiz creator",
    )


class QuizAttemptQuestionAnswerBaseSchema(pydantic.BaseModel):
    """Quiz attempt question answer base schema."""

    answer_index: pydantic.StrictInt = pydantic.Field(
        description="Index of the answer",
    )


class QuizAttemptQuestionAnswerCreateSchema(QuizAttemptQuestionAnswerBaseSchema):
    """Quiz attempt question answer create schema."""

    pass


@partial
class QuizAttemptQuestionAnswerUpdateSchema(QuizAttemptQuestionAnswerBaseSchema):
    """Quiz attempt question answer update schema."""

    pass


class BaseQuizAttemptQuestionAnswerSchema(QuizAttemptQuestionAnswerBaseSchema):
    """Base Quiz attempt question answer schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Quiz attempt question answer unique identifier",
    )
    question: BaseQuestionSchema = pydantic.Field(
        description="Question",
    )
    is_correct: pydantic.StrictBool = pydantic.Field(
        description="Is the answer correct",
    )
    created_at: pydantic.AwareDatetime = pydantic.Field(
        description="Quiz attempt question answer creation datetime",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Quiz attempt question answer update datetime",
    )

    class Config:
        from_attributes = True

    def __hash__(self) -> int:
        return hash(self.uid)


class QuizAttemptQuestionAnswerSchema(BaseQuizAttemptQuestionAnswerSchema):
    """Quiz attempt question answer schema. For serialization purposes only."""

    answered_by: BaseAccountSchema = pydantic.Field(
        description="Quiz attempt question answer creator",
    )


class QuizAttemptBaseSchema(pydantic.BaseModel):
    """Quiz attempt base schema."""

    attempted_questions: pydantic.StrictInt = pydantic.Field(
        description="Number of attempted questions",
    )
    score: typing.Optional[pydantic.StrictInt] = pydantic.Field(
        default=None,
        description="Quiz score",
    )
    submitted: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Is the quiz submitted",
    )
    submitted_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="Quiz submission datetime",
    )


class QuizAttemptCreateSchema(QuizAttemptBaseSchema):
    """Quiz attempt create schema."""

    pass


@partial
class QuizAttemptUpdateSchema(QuizAttemptBaseSchema):
    """Quiz attempt update schema."""

    pass


class BaseQuizAttemptSchema(QuizAttemptBaseSchema):
    """Base Quiz attempt schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Quiz attempt unique identifier",
    )
    quiz: BaseQuizSchema = pydantic.Field(
        description="Quiz",
    )
    attempted_by: BaseAccountSchema = pydantic.Field(description="Quiz attempt creator")
    created_at: pydantic.AwareDatetime = pydantic.Field(
        description="Quiz attempt creation datetime",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Quiz attempt update datetime",
    )

    class Config:
        from_attributes = True

    def __hash__(self) -> int:
        return hash(self.uid)


class QuizAttemptSchema(BaseQuizAttemptSchema):
    """Quiz attempt schema. For serialization purposes only."""

    question_answers: typing.List[BaseQuizAttemptQuestionAnswerSchema] = pydantic.Field(
        description="Quiz attempt question answers",
    )

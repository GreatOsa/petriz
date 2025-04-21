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
    difficulty: QuestionDifficulty = pydantic.Field(
        QuestionDifficulty.NOT_SET,
        description="Question difficulty",
    )
    hint: typing.Optional[pydantic.StrictStr] = pydantic.Field(
        default=None, max_length=2000, description="Question hint"
    )

    @pydantic.field_serializer("options")
    def serialize_options(
        self,
        value: typing.List[str],
        info: pydantic.FieldSerializationInfo,
    ) -> typing.List[str]:
        return [option.strip() for option in value]

    @pydantic.field_serializer("difficulty")
    def serialize_difficulty(
        self,
        value: QuestionDifficulty,
    ) -> str:
        return value.value


class QuestionCreateSchema(QuestionBaseSchema):
    """Question create schema."""

    correct_option_index: typing.Annotated[
        pydantic.StrictInt,
        Interval(ge=0, le=5),
    ] = pydantic.Field(
        description="Index of the correct option",
    )


@partial
class QuestionUpdateSchema(QuestionBaseSchema):
    """Question update schema."""

    correct_option_index: typing.Annotated[
        pydantic.StrictInt,
        Interval(ge=0, le=5),
    ] = pydantic.Field(
        description="Index of the correct option",
    )


class BaseQuestionSchema(QuestionBaseSchema):
    """Base Question schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Question unique identifier",
    )
    version: typing.Optional[pydantic.StrictInt] = pydantic.Field(
        default=None,
        ge=0,
        description="Question version",
    )
    created_at: pydantic.AwareDatetime = pydantic.Field(
        description="Question creation datetime",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Question update datetime",
    )
    deleted_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="Question deletion datetime",
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
    created_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        description="User who created the question",
    )
    deleted_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        default=None,
        description="User who deleted the question",
    )


class QuestionWithAnswerSchema(QuestionSchema):
    """Question schema. For serialization purposes only."""

    correct_option_index: typing.Annotated[
        pydantic.StrictInt,
        Interval(ge=0, le=5),
    ] = pydantic.Field(
        description="Index of the correct option",
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
    duration: typing.Optional[pydantic.PositiveFloat] = pydantic.Field(
        default=None,
        description="Quiz duration in minutes",
    )
    is_public: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Is the quiz public",
    )
    metadata: typing.Optional[typing.Dict[pydantic.StrictStr, pydantic.JsonValue]] = (
        pydantic.Field(
            validation_alias=pydantic.AliasChoices(
                "extradata",
                "metadata",
            ),
            serialization_alias="metadata",
            description="Quiz metadata",
        )
    )


class QuizCreateSchema(QuizBaseSchema):
    """Quiz create schema."""

    questions: typing.List[typing.Union[QuestionCreateSchema, pydantic.StrictStr]] = (
        pydantic.Field(
            description="Quiz questions",
            min_length=1,
            max_length=1000,
        )
    )


@partial
class QuizUpdateSchema(QuizBaseSchema):
    """Quiz update schema."""

    pass


class BaseQuizSchema(QuizBaseSchema):
    """Base Quiz schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Quiz unique identifier",
    )
    version: typing.Optional[pydantic.StrictInt] = pydantic.Field(
        default=None,
        ge=0,
        description="Quiz version",
    )
    questions_count: typing.Optional[pydantic.StrictInt] = pydantic.Field(
        default=None,
        ge=0,
        description="Number of quiz questions",
    )
    difficulty: QuizDifficulty = pydantic.Field(
        QuizDifficulty.NOT_SET, description="Quiz difficulty"
    )
    is_timed: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Is the quiz time constrained?",
    )
    created_at: pydantic.AwareDatetime = pydantic.Field(
        description="Quiz creation datetime",
    )
    updated_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        description="Quiz update datetime",
    )
    deleted_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="Quiz deletion datetime",
    )

    class Config:
        from_attributes = True

    def __hash__(self) -> int:
        return hash(self.uid)

    @pydantic.field_serializer("difficulty")
    def serialize_difficulty(self, value: QuizDifficulty) -> str:
        return value.value


class QuizSchema(BaseQuizSchema):
    """Quiz schema. For serialization purposes only."""

    questions: typing.List[BaseQuestionSchema] = pydantic.Field(
        description="Quiz questions",
    )
    created_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        description="User who created the quiz",
    )
    deleted_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        default=None,
        description="User who deleted the quiz",
    )


class QuizWithQuestionAnswersSchema(BaseQuizSchema):
    """Quiz schema. For serialization purposes only."""

    questions: typing.List[QuestionWithAnswerSchema] = pydantic.Field(
        description="Quiz questions",
    )
    created_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        description="User who created the quiz",
    )
    deleted_by: typing.Optional[BaseAccountSchema] = pydantic.Field(
        default=None,
        description="User who deleted the quiz",
    )


class QuizQuestionAddSchema(pydantic.BaseModel):
    """Schema for adding a question to a quiz."""

    questions: typing.List[typing.Union[QuestionCreateSchema, pydantic.StrictStr]] = (
        pydantic.Field(
            description="Quiz questions",
            min_length=1,
            max_length=1000,
        )
    )


class QuizQuestionRemoveSchema(pydantic.BaseModel):
    """Schema for removing a question from a quiz."""

    questions: typing.List[typing.Annotated[pydantic.StrictStr, MaxLen(50)]] = (
        pydantic.Field(
            description="Quiz questions",
            min_length=1,
            max_length=1000,
        )
    )


class QuizAttemptQuestionAnswerBaseSchema(pydantic.BaseModel):
    """Quiz attempt question answer base schema."""

    answer_index: pydantic.StrictInt = pydantic.Field(
        description="Index of the answer",
    )
    is_final: pydantic.StrictBool = pydantic.Field(
        default=True,
        description="Is this the final answer?",
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
    is_correct: pydantic.StrictBool = pydantic.Field(
        description="Whether the answer is correct as of the the time the question was answered",
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

    question: QuestionSchema = pydantic.Field(
        description="The question answered.",
    )
    answered_by: BaseAccountSchema = pydantic.Field(
        description="Who gave the question answer?",
    )


class QuizAttemptBaseSchema(pydantic.BaseModel):
    """Quiz attempt base schema."""

    is_submitted: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Is the quiz submitted",
    )


# @partial
class QuizAttemptUpdateSchema(QuizAttemptBaseSchema):
    """Quiz attempt update schema."""

    pass


class BaseQuizAttemptSchema(QuizAttemptBaseSchema):
    """Base Quiz attempt schema. For serialization purposes only."""

    uid: typing.Annotated[pydantic.StrictStr, MaxLen(50)] = pydantic.Field(
        description="Quiz attempt unique identifier",
    )
    quiz: BaseQuizSchema = pydantic.Field(
        description="The quiz attempted.",
    )
    duration: typing.Optional[pydantic.PositiveFloat] = pydantic.Field(
        default=None,
        ge=0,
        description="Quiz attempt duration in minutes",
    )
    is_timed: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Is the quiz attempt time constrained?",
    )
    time_remaining: typing.Optional[pydantic.PositiveFloat] = pydantic.Field(
        default=None,
        ge=0,
        description="Quiz attempt time remaining in seconds",
    )
    is_expired: pydantic.StrictBool = pydantic.Field(
        default=False,
        description="Has the quiz attempt duration elapsed?",
    )
    attempted_questions: pydantic.StrictInt = pydantic.Field(
        description="Number of attempted questions",
    )
    score: typing.Optional[pydantic.StrictInt] = pydantic.Field(
        default=None,
        description="Quiz score",
    )
    attempted_by: BaseAccountSchema = pydantic.Field(description="Quiz attempt creator")
    submitted_at: typing.Optional[pydantic.AwareDatetime] = pydantic.Field(
        default=None,
        description="Quiz submission datetime",
    )
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

    question_answers: typing.List[QuizAttemptQuestionAnswerSchema] = pydantic.Field(
        description="Quiz attempt question answers",
    )

import datetime
import typing
import uuid
import enum
from annotated_types import MaxLen
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import TSVECTOR
from helpers.fastapi.sqlalchemy import models, mixins

from api.utils import generate_uid
from apps.accounts.models import Account
from apps.search.models import Topic, Term
from helpers.fastapi.utils import timezone


def generate_quiz_uid() -> str:
    return generate_uid(prefix="petriz_quiz_")


def generate_question_uid() -> str:
    return generate_uid(prefix="petriz_question_")


def generate_quiz_attempt_uid() -> str:
    return generate_uid(prefix="petriz_quiz_attempt_")


def generate_quiz_attempt_question_answer_uid() -> str:
    return generate_uid(prefix="petriz_quiz_attempt_question_answer_")


class QuizDifficulty(enum.Enum):
    """Enum for quiz difficulty levels."""

    NOT_SET = "not_set"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionDifficulty(enum.Enum):
    """Enum for question difficulty levels."""

    NOT_SET = "not_set"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionToTopicAssociation(models.Model):
    """Model for question to topic many-to-many association."""

    __auto_tablename__ = True

    question_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__questions.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the question.",
    )
    topic_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("search__topics.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the topic.",
    )

    __table_args__ = (sa.UniqueConstraint("question_id", "topic_id"),)


class QuestionToTermAssociation(models.Model):
    """Model for question to term many-to-many association."""

    __auto_tablename__ = True

    question_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__questions.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the question.",
    )
    term_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("search__terms.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the term.",
    )

    __table_args__ = (sa.UniqueConstraint("question_id", "term_id"),)


class QuestionToQuizAssociation(models.Model):
    """Model for question to quiz many-to-many association."""

    __auto_tablename__ = True

    question_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__questions.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the question.",
    )
    quiz_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__quizzes.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the quiz.",
    )

    __table_args__ = (sa.UniqueConstraint("question_id", "quiz_id"),)


class Question(mixins.TimestampMixin, models.Model):
    """Model for quiz questions."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        unique=False,
        index=True,
        default=generate_question_uid,
        doc="Unique ID of the question.",
    )
    version: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("version >= 0"),
        default=0,
        server_default=sa.text("0"),
        doc="Version of the question.",
    )
    is_latest: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=True,
        doc="Whether the question is the latest version.",
        index=True,
        server_default=sa.true(),
    )
    question: orm.Mapped[str] = orm.mapped_column(sa.Text, doc="Question text.")
    options: orm.Mapped[typing.List[typing.Annotated[str, MaxLen(500)]]] = (
        orm.mapped_column(
            sa.ARRAY(sa.String(500), dimensions=1),
            doc="List of options for the question.",
        )
    )
    correct_option_index: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("correct_option_index >= 0"),
        doc="Index of the correct option.",
    )
    difficulty: orm.Mapped[str] = orm.mapped_column(
        sa.String(20),
        default=QuestionDifficulty.NOT_SET.value,
        doc="Difficulty level of the question.",
        index=True,
    )
    hint: orm.Mapped[str] = orm.mapped_column(
        sa.Text, nullable=True, doc="Hint for the question."
    )
    search_tsvector = orm.mapped_column(
        TSVECTOR,
        nullable=True,
        doc="Full-text search vector for the question.",
    )
    created_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Unique ID of the user who created the question.",
    )
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean, default=False, doc="Whether the question is deleted.", index=True
    )
    deleted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the question was deleted.",
    )
    deleted_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
        doc="Unique ID of the user who deleted the question.",
    )

    ######### Relationships #############
    created_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        Account,
        foreign_keys=[created_by_id],
        uselist=False,
        doc="User who created the question.",
    )
    deleted_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        Account,
        foreign_keys=[deleted_by_id],
        uselist=False,
        doc="User who deleted the question.",
    )
    quizzes: orm.Mapped[typing.Set["Quiz"]] = orm.relationship(
        "Quiz",
        secondary=QuestionToQuizAssociation.__table__,  # type: ignore
        back_populates="questions",
        lazy="selectin",
        doc="Quizzes to which the question belongs.",
    )
    related_topics: orm.Mapped[typing.Set[Topic]] = orm.relationship(
        Topic,
        secondary=QuestionToTopicAssociation.__table__,  # type: ignore
        doc="Topics associated with the question.",
        lazy="selectin",
        order_by=Topic.name.asc(),
    )
    related_terms: orm.Mapped[typing.Set[Term]] = orm.relationship(
        Term,
        secondary=QuestionToTermAssociation.__table__,  # type: ignore
        doc="Terms associated with the question.",
        lazy="selectin",
        order_by=Term.name.asc(),
    )

    DEFAULT_ORDERING = (sa.desc("created_at"),)

    __table_args__ = (
        sa.UniqueConstraint("uid", "version", name="uq_question_uid_version"),
        sa.Index("ix_question_created_at", "created_at"),
        sa.Index(
            "ix_question_search_tsvector", "search_tsvector", postgresql_using="gin"
        ),
    )

    @orm.validates("options")
    def validate_options(self, key: str, value: typing.List[str]) -> typing.List[str]:
        no_of_options = len(value)
        if no_of_options < 2:
            raise ValueError("At least two options are required.")
        if no_of_options != len(set(value)):
            raise ValueError("Options must be unique.")
        if no_of_options > 6:
            raise ValueError("Maximum 6 options are allowed")
        return value

    @orm.validates("correct_option_index")
    def validate_correct_option_index(self, key: str, value: int) -> int:
        if value < 0 or value >= len(self.options):
            raise ValueError("Invalid correct option index.")
        return value

    difficulty_levels = [
        level.value for level in QuestionDifficulty.__members__.values()
    ]

    @orm.validates("difficulty")
    def validate_difficulty(self, key: str, value: str) -> str:
        if value not in self.difficulty_levels:
            raise ValueError(f"Invalid difficulty level: {value}")
        return value


class Quiz(mixins.TimestampMixin, models.Model):
    """Model for quizzes."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        unique=False,
        index=True,
        default=generate_quiz_uid,
        doc="Unique ID of the quiz.",
    )
    version: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("version >= 0"),
        default=0,
        server_default=sa.text("0"),
        doc="Version of the quiz.",
    )
    is_latest: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=True,
        server_default=sa.true(),
        doc="Whether the quiz is the latest version.",
        index=True,
    )
    title: orm.Mapped[str] = orm.mapped_column(
        sa.String(255), index=True, doc="Title of the quiz."
    )
    description: orm.Mapped[str] = orm.mapped_column(
        sa.Text, nullable=True, doc="Description of the quiz."
    )
    difficulty: orm.Mapped[str] = orm.mapped_column(
        sa.String(20),
        default=QuizDifficulty.NOT_SET.value,
        doc="Difficulty level of the quiz.",
        index=True,
    )
    search_tsvector = orm.mapped_column(
        TSVECTOR,
        nullable=True,
        doc="Full-text search vector for the quiz.",
    )
    questions: orm.Mapped[typing.Set[Question]] = orm.relationship(
        "Question",
        secondary=QuestionToQuizAssociation.__table__,  # type: ignore
        back_populates="quizzes",
        lazy="selectin",
        doc="Questions in the quiz.",
    )
    created_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        doc="Unique ID of the user who created the quiz.",
    )
    extradata: orm.Mapped[typing.Dict[str, typing.Any]] = orm.mapped_column(
        sa.JSON,
        doc="Additional data associated with the quiz.",
        nullable=True,
    )
    duration: orm.Mapped[typing.Optional[float]] = orm.mapped_column(
        sa.Float(2),
        sa.CheckConstraint("duration >= 0"),
        nullable=True,
        index=True,
        doc="Duration of the quiz in minutes.",
    )
    questions_count: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("questions_count >= 0"),
        default=0,
        doc="Number of questions in the quiz.",
    )
    is_public: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
        server_default=sa.false(),
        doc="Whether the quiz is public.",
        index=True,
    )
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
        server_default=sa.false(),
        doc="Whether the quiz is deleted.",
        index=True,
    )
    deleted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the quiz was deleted.",
    )
    deleted_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        nullable=True,
        doc="Unique ID of the user who deleted the quiz.",
    )

    ######### Relationships #############
    created_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        Account,
        foreign_keys=[created_by_id],
        back_populates="quizzes",
        uselist=False,
        doc="User who created the quiz.",
    )
    deleted_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        Account,
        foreign_keys=[deleted_by_id],
        uselist=False,
        doc="User who deleted the quiz.",
    )
    attempts: orm.Mapped[typing.List["QuizAttempt"]] = orm.relationship(
        "QuizAttempt",
        back_populates="quiz",
        lazy="dynamic",
        doc="Attempts made on the quiz.",
        order_by="QuizAttempt.created_at",
    )

    __table_args__ = (
        sa.UniqueConstraint("uid", "version", name="uq_quiz_uid_version"),
        sa.UniqueConstraint("title", "created_by_id"),
        sa.Index("ix_quiz_created_at", "created_at"),
        sa.Index("ix_quiz_updated_at", "updated_at"),
        sa.Index("ix_quiz_search_tsvector", "search_tsvector", postgresql_using="gin"),
    )
    DEFAULT_ORDERING = (
        sa.desc("created_at"),
        sa.asc("title"),
    )

    difficulty_levels = [level.value for level in QuizDifficulty.__members__.values()]

    @orm.validates("difficulty")
    def validate_difficulty(self, key: str, value: str) -> str:
        if value not in self.difficulty_levels:
            raise ValueError(f"Invalid difficulty level: {value}")
        return value

    @orm.validates("duration")
    def validate_duration(
        self, key: str, value: typing.Optional[float]
    ) -> typing.Optional[float]:
        if value is not None and value < 0:
            raise ValueError("Duration cannot be negative.")
        return value

    @orm.validates("questions_count")
    def validate_questions_count(self, key: str, value: int) -> int:
        if value < 0:
            raise ValueError("Questions count cannot be negative.")
        return value

    @property
    def is_timed(self) -> bool:
        return self.duration is not None


class QuizAttempt(mixins.TimestampMixin, models.Model):
    """Model for quiz attempts."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        unique=True,
        index=True,
        default=generate_quiz_attempt_uid,
        doc="Unique ID of the quiz attempt.",
    )
    quiz_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__quizzes.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the quiz.",
    )
    duration: orm.Mapped[typing.Optional[float]] = orm.mapped_column(
        sa.Float(2),
        sa.CheckConstraint("duration >= 0"),
        nullable=True,
        doc="Duration of the quiz attempt in minutes.",
    )
    attempted_by_id: orm.Mapped[uuid.UUID] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the user who attempted the quiz.",
    )
    attempted_questions: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("attempted_questions >= 0"),
        default=0,
        doc="Number of questions attempted by the user. Auto-updated by postgres trigger",
    )
    score: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("score >= 0"),
        nullable=True,
        doc="Score obtained by the user.",
        index=True,
    )
    is_submitted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
        server_default=sa.false(),
        doc="Whether the quiz attempt is submitted.",
        index=True,
    )
    submitted_at: orm.Mapped[typing.Optional[datetime.datetime]] = orm.mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        doc="Datetime when the quiz attempt was submitted.",
    )

    ######### Relationships #############
    quiz: orm.Mapped[Quiz] = orm.relationship(
        Quiz,
        back_populates="attempts",
        doc="Quiz attempted by the user.",
    )
    attempted_by: orm.Mapped[Account] = orm.relationship(
        Account,
        doc="User who attempted the quiz.",
    )
    question_answers: orm.Mapped[typing.Set["QuizAttemptQuestionAnswer"]] = (
        orm.relationship(
            "QuizAttemptQuestionAnswer",
            back_populates="quiz_attempt",
            doc="Answers given by the user in the quiz attempt.",
            order_by="QuizAttemptQuestionAnswer.created_at",
            lazy="selectin",
        )
    )

    __table_args__ = (
        sa.Index(
            "ix_quiz_attempt_quiz_id_attempted_by_id", "quiz_id", "attempted_by_id"
        ),
        sa.Index("ix_quiz_attempt_created_at", "created_at"),
    )
    DEFAULT_ORDERING = (sa.desc("created_at"),)

    @orm.validates("score")
    def validate_score(self, key: str, value: int) -> int:
        if value < 0:
            raise ValueError("Score cannot be negative.")
        return value

    @orm.validates("duration")
    def validate_duration(
        self, key: str, value: typing.Optional[float]
    ) -> typing.Optional[float]:
        if value is not None and value < 0:
            raise ValueError("Duration cannot be negative.")
        return value

    @orm.validates("attempted_questions")
    def validate_attempted_questions(self, key: str, value: int) -> int:
        if value < 0:
            raise ValueError("Number of attempted questions cannot be negative.")
        return value

    @orm.validates("submitted_at")
    def validate_submitted_at(
        self, key: str, value: typing.Optional[datetime.datetime]
    ) -> typing.Optional[datetime.datetime]:
        if value and value > timezone.now():
            raise ValueError("Submitted datetime cannot be in the future.")
        return value

    @property
    def is_timed(self) -> bool:
        return bool(self.duration)

    @property
    def time_remaining(self) -> typing.Optional[float]:
        """Calculate the time remaining for the quiz attempt in seconds."""
        if self.duration:
            if self.is_submitted:
                return 0.00

            elapsed_time = (timezone.now() - self.created_at).total_seconds()
            remaining_time = (self.duration * 60) - elapsed_time
            return max(0.00, remaining_time)
        return None

    @property
    def is_expired(self) -> bool:
        """Check if the quiz attempt is expired."""
        if self.duration:
            return self.time_remaining <= 0.00  # type: ignore
        return False


class QuizAttemptQuestionAnswer(mixins.TimestampMixin, models.Model):
    """Model for quiz attempt question answers."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        unique=True,
        index=True,
        default=generate_quiz_attempt_question_answer_uid,
        doc="Unique ID of the quiz attempt question answer.",
    )
    answer_index: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("answer_index >= 0"),
        doc="Answer to the question.",
    )
    is_final: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
        server_default=sa.false(),
        doc="Whether the answer is final.",
        index=True,
    )
    is_correct: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
        server_default=sa.false(),
        doc="Whether the answer is correct as of the time the question was answered.",
        index=True,
    )
    question_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__questions.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the question.",
    )
    quiz_attempt_id: orm.Mapped[int] = orm.mapped_column(
        sa.Integer,
        sa.ForeignKey("quizzes__quiz_attempts.id", ondelete="CASCADE"),
        index=True,
        doc="Unique ID of the quiz attempt.",
    )
    answered_by_id: orm.Mapped[typing.Optional[uuid.UUID]] = orm.mapped_column(
        sa.UUID,
        sa.ForeignKey("accounts__client_accounts.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        doc="Unique ID of the user who answered the question.",
    )

    ######### Relationships #############
    question: orm.Mapped[Question] = orm.relationship(
        Question,
        doc="Question to which the answer belongs.",
    )
    quiz_attempt: orm.Mapped[QuizAttempt] = orm.relationship(
        QuizAttempt,
        back_populates="question_answers",
        doc="Quiz attempt to which the answer belongs.",
    )
    answered_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        Account,
        uselist=False,
        doc="User who answered the question.",
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "question_id",
            "quiz_attempt_id",
            "answered_by_id",
            name="uq_quiz_attempt_question_answer",
        ),
        sa.Index(
            "ix_quiz_atmpt_questn_answr_questn_id_quiz_atmpt_id_answrd_by_id",
            "question_id",
            "quiz_attempt_id",
            "answered_by_id",
        ),
        sa.Index(
            "ix_quiz_atmpt_questn_answr_questn_answrd_by_id_ctd_at",
            "question_id",
            "answered_by_id",
            "created_at",
        ),
        sa.Index(
            "ix_quiz_attempt_question_answer_created_at",
            "created_at",
        ),
    )

    DEFAULT_ORDERING = (sa.asc("created_at"),)

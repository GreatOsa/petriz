import datetime
import typing
import uuid
import logging
import enum
import multiprocessing
from annotated_types import MaxLen
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import TSVECTOR
from helpers.fastapi.sqlalchemy import models, mixins, setup

from api.utils import generate_uid
from apps.accounts.models import Account
from apps.search.models import Topic, Term
from helpers.fastapi.utils import timezone


logger = logging.getLogger(__name__)


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
        unique=True,
        index=True,
        default=generate_question_uid,
        doc="Unique ID of the question.",
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
    difficulty: orm.Mapped[QuestionDifficulty] = orm.mapped_column(
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
    quizzes: orm.Mapped[typing.Set["Quiz"]] = orm.relationship(
        "Quiz",
        secondary=QuestionToQuizAssociation.__table__,  # type: ignore
        back_populates="questions",
        doc="Quizzes to which the question belongs.",
    )
    related_topics: orm.Mapped[typing.Set[Topic]] = orm.relationship(
        Topic,
        secondary=QuestionToTopicAssociation.__table__,  # type: ignore
        doc="Topics associated with the question.",
        order_by="Topic.name",
    )
    related_terms: orm.Mapped[typing.Set[Term]] = orm.relationship(
        Term,
        secondary=QuestionToTermAssociation.__table__,  # type: ignore
        doc="Terms associated with the question.",
        order_by="Term.name",
    )

    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean, default=False, doc="Whether the question is deleted.", index=True
    )

    DEFAULT_ORDERING = (sa.desc("created_at"),)

    __table_args__ = (
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

    @orm.validates("difficulty")
    def validate_difficulty(self, key: str, value: str) -> str:
        if value not in QuestionDifficulty.__members__.values():
            raise ValueError(f"Invalid difficulty level: {value}")
        return value


class Quiz(mixins.TimestampMixin, models.Model):
    """Model for quizzes."""

    __auto_tablename__ = True

    uid: orm.Mapped[typing.Annotated[str, MaxLen(50)]] = orm.mapped_column(
        sa.String(50),
        unique=True,
        index=True,
        default=generate_quiz_uid,
        doc="Unique ID of the quiz.",
    )
    title: orm.Mapped[str] = orm.mapped_column(
        sa.String(255), index=True, doc="Title of the quiz."
    )
    description: orm.Mapped[str] = orm.mapped_column(
        sa.Text, nullable=True, doc="Description of the quiz."
    )
    difficulty: orm.Mapped[QuizDifficulty] = orm.mapped_column(
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
    data: orm.Mapped[typing.Dict[str, typing.Any]] = orm.mapped_column(
        sa.JSON, doc="Additional data associated with the quiz."
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
        sa.Boolean, default=False, doc="Whether the quiz is public.", index=True
    )
    is_deleted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean, default=False, doc="Whether the quiz is deleted.", index=True
    )

    ######### Relationships #############
    created_by: orm.Mapped[typing.Optional[Account]] = orm.relationship(
        "Account",
        back_populates="quizzes",
        uselist=False,
        doc="User who created the quiz.",
    )
    attempts: orm.Mapped[typing.List["QuizAttempt"]] = orm.relationship(
        "QuizAttempt",
        back_populates="quiz",
        lazy="dynamic",
        doc="Attempts made on the quiz.",
        order_by="QuizAttempt.created_at",
    )

    __table_args__ = (
        sa.UniqueConstraint("title", "created_by_id"),
        sa.Index("ix_quiz_created_at", "created_at"),
        sa.Index("ix_quiz_updated_at", "updated_at"),
        sa.Index("ix_quiz_search_tsvector", "search_tsvector", postgresql_using="gin"),
    )
    DEFAULT_ORDERING = (
        sa.desc("created_at"),
        sa.asc("name"),
    )

    @orm.validates("difficulty")
    def validate_difficulty(self, key: str, value: str) -> str:
        if value not in QuizDifficulty.__members__.values():
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
        doc="Number of questions attempted by the user.",
    )
    score: orm.Mapped[typing.Optional[int]] = orm.mapped_column(
        sa.Integer,
        sa.CheckConstraint("score >= 0"),
        nullable=True,
        doc="Score obtained by the user.",
        index=True,
    )
    submitted: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
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
            lazy="dynamic",
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
            if self.submitted:
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
        doc="Whether the answer is final.",
        index=True,
    )
    is_correct: orm.Mapped[bool] = orm.mapped_column(
        sa.Boolean,
        default=False,
        doc="Whether the answer is correct as of the time the question was answered.",
        index=True,
    )
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
    quiz: orm.Mapped[Quiz] = orm.relationship(
        Quiz,
        doc="Quiz to which the answer belongs.",
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
            "ix_quiz_atmpt_questn_answr_quiz_questn_answrd_by_id_ctd_at",
            "quiz_id",
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


# Constants for search configuration
QUIZ_SEARCH_CONFIG = {
    "language": "pg_catalog.english",
    "weights": {
        "title": "A",
        "description": "B",
        "difficulty": "C",
    },
}

QUESTION_SEARCH_CONFIG = {
    "language": "pg_catalog.english",
    "weights": {
        "question": "A",
        "hint": "B",
        "options": "C",
        "difficulty": "D",
    },
}

QUIZ_SEARCH_VECTOR_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS quizzes_search_tsvector_update ON {Quiz.__tablename__};
    DROP FUNCTION IF EXISTS update_quizzes_search_tsvector();
    DROP FUNCTION IF EXISTS backfill_quizzes_tsvectors();
    """),
    # Create backfill functions
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION backfill_quizzes_tsvectors() RETURNS void AS 
    $$
    DECLARE
        quizzes_count integer;
    BEGIN
        UPDATE {Quiz.__tablename__}
        SET search_tsvector = 
            setweight(to_tsvector('{QUIZ_SEARCH_CONFIG["language"]}', coalesce(title, '')), '{QUIZ_SEARCH_CONFIG["weights"]["title"]}') ||
            setweight(to_tsvector('{QUIZ_SEARCH_CONFIG["language"]}', coalesce(description, '')), '{QUIZ_SEARCH_CONFIG["weights"]["description"]}') ||
            setweight(to_tsvector('{QUIZ_SEARCH_CONFIG["language"]}', coalesce(difficulty, '')), '{QUIZ_SEARCH_CONFIG["weights"]["difficulty"]}')
        WHERE search_tsvector IS NULL;

        GET DIAGNOSTICS quizzes_count = ROW_COUNT;
        RAISE NOTICE 'Updated %% quiz records', quizzes_count;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Backfill failed for quizzes: %%', SQLERRM;
    END;
    $$ LANGUAGE plpgsql;
    """),
    # Create trigger functions
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_quizzes_search_tsvector() RETURNS trigger AS 
    $$
    BEGIN
        NEW.search_tsvector := 
            setweight(to_tsvector('{QUIZ_SEARCH_CONFIG["language"]}', coalesce(NEW.title, '')), '{QUIZ_SEARCH_CONFIG["weights"]["title"]}') ||
            setweight(to_tsvector('{QUIZ_SEARCH_CONFIG["language"]}', coalesce(NEW.description, '')), '{QUIZ_SEARCH_CONFIG["weights"]["description"]}') ||
            setweight(to_tsvector('{QUIZ_SEARCH_CONFIG["language"]}', coalesce(NEW.difficulty, '')), '{QUIZ_SEARCH_CONFIG["weights"]["difficulty"]}');
        RETURN NEW;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Failed to update quiz tsvector: %%', SQLERRM;
        NEW.search_tsvector := NULL;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    # Create triggers
    sa.DDL(f"""
    CREATE TRIGGER quizzes_search_tsvector_update
        BEFORE INSERT OR UPDATE OF title, description, difficulty ON {Quiz.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_quizzes_search_tsvector();
    """),
    # Execute backfill
    sa.DDL("SELECT backfill_quizzes_tsvectors();"),
)


QUESTION_SEARCH_VECTOR_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS questions_search_tsvector_update ON {Question.__tablename__};
    DROP FUNCTION IF EXISTS update_questions_search_tsvector();
    DROP FUNCTION IF EXISTS backfill_questions_tsvectors();
    """),
    # Create backfill functions
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION backfill_questions_tsvectors() RETURNS void AS 
    $$
    DECLARE
        questions_count integer;
    BEGIN
        UPDATE {Question.__tablename__}
        SET search_tsvector = 
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(question, '')), '{QUESTION_SEARCH_CONFIG["weights"]["question"]}') ||
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(hint, '')), '{QUESTION_SEARCH_CONFIG["weights"]["hint"]}') ||
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(array_to_string(options, ' '), '')), '{QUESTION_SEARCH_CONFIG["weights"]["options"]}') ||
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(difficulty, '')), '{QUESTION_SEARCH_CONFIG["weights"]["difficulty"]}')
        WHERE search_tsvector IS NULL;

        GET DIAGNOSTICS questions_count = ROW_COUNT;
        RAISE NOTICE 'Updated %% question records', questions_count;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Backfill failed for questions: %%', SQLERRM;
    END;
    $$ LANGUAGE plpgsql;
    """),
    # Create trigger functions
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_questions_search_tsvector() RETURNS trigger AS 
    $$
    BEGIN
        NEW.search_tsvector := 
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(NEW.question, '')), '{QUESTION_SEARCH_CONFIG["weights"]["question"]}') ||
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(NEW.hint, '')), '{QUESTION_SEARCH_CONFIG["weights"]["hint"]}') ||
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(array_to_string(NEW.options, ' '), '')), '{QUESTION_SEARCH_CONFIG["weights"]["options"]}') ||
            setweight(to_tsvector('{QUESTION_SEARCH_CONFIG["language"]}', coalesce(NEW.difficulty, '')), '{QUESTION_SEARCH_CONFIG["weights"]["difficulty"]}');
        RETURN NEW;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'Failed to update question tsvector: %%', SQLERRM;
        NEW.search_tsvector := NULL;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    sa.DDL(f"""
    CREATE TRIGGER questions_search_tsvector_update
        BEFORE INSERT OR UPDATE OF question, hint, options, difficulty ON {Question.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_questions_search_tsvector();
    """),
    # Execute backfill
    sa.DDL("SELECT backfill_questions_tsvectors();"),
)


QUIZ_ATTEMPT_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS update_attempted_questions_trigger ON {QuizAttemptQuestionAnswer.__tablename__};
    DROP FUNCTION IF EXISTS update_attempted_questions();
    """),
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_attempted_questions() RETURNS trigger AS 
    $$
    BEGIN
        UPDATE {QuizAttempt.__tablename__}
        SET attempted_questions = (
            SELECT COUNT(DISTINCT question_id)
            FROM {QuizAttemptQuestionAnswer.__tablename__}
            WHERE quiz_attempt_id = NEW.quiz_attempt_id
        )
        WHERE id = NEW.quiz_attempt_id;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    sa.DDL(f"""
    CREATE TRIGGER update_attempted_questions_trigger
        AFTER INSERT OR UPDATE ON {QuizAttemptQuestionAnswer.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_attempted_questions();
    """),
)


QUIZ_QUESTION_COUNT_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS update_questions_count_trigger ON {QuestionToQuizAssociation.__tablename__};
    DROP TRIGGER IF EXISTS update_questions_count_on_question_update_trigger ON {Question.__tablename__};
    DROP FUNCTION IF EXISTS update_questions_count();
    """),
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_questions_count() RETURNS trigger AS 
    $$
    BEGIN
        UPDATE {Quiz.__tablename__}
        SET questions_count = (
            SELECT COUNT(*)
            FROM {QuestionToQuizAssociation.__tablename__} AS assoc
            JOIN {Question.__tablename__} AS q
            ON assoc.question_id = q.id
            WHERE assoc.quiz_id = NEW.quiz_id AND q.is_deleted = FALSE
        )
        WHERE id = NEW.quiz_id;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    sa.DDL(f"""
    CREATE TRIGGER update_questions_count_trigger
        AFTER INSERT OR DELETE ON {QuestionToQuizAssociation.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_questions_count();
    """),
    sa.DDL(f"""
    CREATE TRIGGER update_questions_count_on_question_update_trigger
        AFTER UPDATE OF is_deleted ON {Question.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_questions_count();
    """),
)


# Trigger function to update the score field in QuizAttempt on QuizAttemptQuestionAnswer insert/update
QUIZ_ATTEMPT_SCORE_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS update_quiz_attempt_score_on_final_trigger ON {QuizAttemptQuestionAnswer.__tablename__};
    DROP TRIGGER IF EXISTS update_quiz_attempt_score_on_correct_trigger ON {QuizAttemptQuestionAnswer.__tablename__};
    DROP FUNCTION IF EXISTS update_quiz_attempt_score();
    """),
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_quiz_attempt_score() RETURNS trigger AS 
    $$
    BEGIN
        UPDATE {QuizAttempt.__tablename__}
        SET score = (
            SELECT COUNT(*)
            FROM {QuizAttemptQuestionAnswer.__tablename__}
            WHERE quiz_attempt_id = NEW.quiz_attempt_id AND is_correct = TRUE
        )
        WHERE id = NEW.quiz_attempt_id;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    sa.DDL(f"""
    CREATE TRIGGER update_quiz_attempt_score_on_final_trigger
        AFTER INSERT OR UPDATE OF is_final ON {QuizAttemptQuestionAnswer.__tablename__}
        FOR EACH ROW
        WHEN (NEW.is_final = TRUE)
        EXECUTE FUNCTION update_quiz_attempt_score();
    """),
    # Add this just to be safe incase `is_correct` is updated even after `is_final` is set to true.
    # So that the attempt score remains accurate.
    sa.DDL(f"""
    CREATE TRIGGER update_quiz_attempt_score_on_correct_trigger
        AFTER UPDATE OF is_correct ON {QuizAttemptQuestionAnswer.__tablename__}
        FOR EACH ROW
        WHEN (NEW.is_final = TRUE)
        EXECUTE FUNCTION update_quiz_attempt_score();
    """),
)


QUIZ_DDLS = (
    *QUIZ_SEARCH_VECTOR_DDLS,
    *QUESTION_SEARCH_VECTOR_DDLS,
    *QUIZ_ATTEMPT_DDLS,
    *QUIZ_QUESTION_COUNT_DDLS,
    *QUIZ_ATTEMPT_SCORE_DDLS,
)


def execute_quiz_ddls():
    """Execute quiz-related DDL statements once during application startup."""
    # Prevents multiple workers from executing DDLs concurrently which
    # may trigger deadlocks from the process trying to acquire AccessExclusiveLock
    # on the same database object(table) at the same time
    with multiprocessing.Lock(), setup.engine.begin() as conn:
        try:
            for ddl in QUIZ_DDLS:
                conn.execute(ddl)
            conn.execute(sa.text("COMMIT"))
            logger.info("Successfully executed quiz DDL statements")
        except Exception as exc:
            logger.error(f"Failed to execute quiz DDL statements: {exc}")
            raise


__all__ = ["Question", "Quiz", "execute_quiz_ddls"]

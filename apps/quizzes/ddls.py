import multiprocessing
import logging
import sqlalchemy as sa

from helpers.fastapi.sqlalchemy import setup
from apps.quizzes.models import (
    Quiz,
    Question,
    QuizAttempt,
    QuizAttemptQuestionAnswer,
    QuestionToQuizAssociation,
)


logger = logging.getLogger(__name__)

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


# Update the trigger function to handle DELETE operations using OLD
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
        -- Use OLD for DELETE operations
        IF (TG_OP = 'DELETE') THEN
            UPDATE {Quiz.__tablename__}
            SET questions_count = (
                SELECT COUNT(*)
                FROM {QuestionToQuizAssociation.__tablename__} AS assoc
                JOIN {Question.__tablename__} AS q
                ON assoc.question_id = q.id
                WHERE assoc.quiz_id = OLD.quiz_id AND q.is_deleted = FALSE
            )
            WHERE id = OLD.quiz_id;
        ELSE
            UPDATE {Quiz.__tablename__}
            SET questions_count = (
                SELECT COUNT(*)
                FROM {QuestionToQuizAssociation.__tablename__} AS assoc
                JOIN {Question.__tablename__} AS q
                ON assoc.question_id = q.id
                WHERE assoc.quiz_id = NEW.quiz_id AND q.is_deleted = FALSE
            )
            WHERE id = NEW.quiz_id;
        END IF;
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


QUIZ_VERSION_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS update_quiz_version_trigger ON {Quiz.__tablename__};
    DROP FUNCTION IF EXISTS update_quiz_version();
    """),
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_quiz_version() RETURNS trigger AS 
    $$
    BEGIN
        NEW.version := (
            SELECT COALESCE(MAX(version), -1) + 1
            FROM {Quiz.__tablename__}
            WHERE uid = NEW.uid
        );
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    sa.DDL(f"""
    CREATE TRIGGER update_quiz_version_trigger
        BEFORE INSERT ON {Quiz.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_quiz_version();
    """),
)

QUESTION_VERSION_DDLS = (
    sa.DDL(f"""
    DROP TRIGGER IF EXISTS update_question_version_trigger ON {Question.__tablename__};
    DROP FUNCTION IF EXISTS update_question_version();
    """),
    sa.DDL(f"""
    CREATE OR REPLACE FUNCTION update_question_version() RETURNS trigger AS 
    $$
    BEGIN
        NEW.version := (
            SELECT COALESCE(MAX(version), -1) + 1
            FROM {Question.__tablename__}
            WHERE uid = NEW.uid
        );
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """),
    sa.DDL(f"""
    CREATE TRIGGER update_question_version_trigger
        BEFORE INSERT ON {Question.__tablename__}
        FOR EACH ROW
        EXECUTE FUNCTION update_question_version();
    """),
)


QUIZ_DDLS = (
    *QUIZ_SEARCH_VECTOR_DDLS,
    *QUESTION_SEARCH_VECTOR_DDLS,
    *QUIZ_ATTEMPT_DDLS,
    *QUIZ_QUESTION_COUNT_DDLS,
    *QUIZ_ATTEMPT_SCORE_DDLS,
    *QUIZ_VERSION_DDLS,
    *QUIZ_VERSION_DDLS,
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

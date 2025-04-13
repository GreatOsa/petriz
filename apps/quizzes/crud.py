import typing
import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import func
from apps.accounts.models import Account
from apps.quizzes.models import Quiz, Question, QuizAttempt, QuizAttemptQuestionAnswer
from apps.search.models import Topic, Term
from helpers.fastapi.sqlalchemy.utils import text_to_tsquery


async def retrieve_question_by_uid(
    session: AsyncSession, uid: str
) -> typing.Optional[Question]:
    """
    Retrieve a question by its UID.
    """
    result = await session.execute(
        sa.select(Question).filter(Question.uid == uid, ~Question.is_deleted)
    )
    return result.scalar_one_or_none()


async def retrieve_quiz_by_uid(
    session: AsyncSession,
    uid: str,
    for_update: bool = False,
) -> typing.Optional[Quiz]:
    """
    Retrieve a quiz by its UID.

    :param session: The database session.
    :param uid: The UID of the quiz to retrieve.
    :return: The quiz object if found, otherwise None.
    """
    query = (
        sa.select(Quiz)
        .where(
            Quiz.uid == uid,
            ~Quiz.is_deleted,
        )
        .options(
            joinedload(Quiz.created_by.and_(~Account.is_deleted)),
            selectinload(Quiz.questions.and_(~Question.is_deleted)),
        )
    )
    if for_update:
        query = query.with_for_update(nowait=True, read=True)

    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_quiz(session: AsyncSession, **create_kwargs) -> Quiz:
    quiz = Quiz(**create_kwargs)
    session.add(quiz)
    return quiz


async def create_question(session: AsyncSession, **create_kwargs) -> Question:
    question = Question(**create_kwargs)
    session.add(question)
    return question


async def bulk_create_questions(
    session: AsyncSession, questions: typing.Sequence[Question]
) -> typing.Sequence[Question]:
    session.add_all(questions)
    await session.flush()
    return questions


async def search_quizzes(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    created_by_id: typing.Optional[uuid.UUID] = None,
    difficulty: typing.Optional[typing.List[str]] = None,
    title: typing.Optional[str] = None,
    duration_gte: typing.Optional[float] = None,
    duration_lte: typing.Optional[float] = None,
    created_at_gte: typing.Optional[datetime.datetime] = None,
    created_at_lte: typing.Optional[datetime.datetime] = None,
    updated_at_gte: typing.Optional[datetime.datetime] = None,
    updated_at_lte: typing.Optional[datetime.datetime] = None,
    limit: int = 100,
    offset: int = 0,
    exclude: typing.Optional[typing.List[typing.Union[str, int]]] = None,
    ordering: typing.Sequence[sa.UnaryExpression] = Quiz.DEFAULT_ORDERING,
    **filters,
) -> typing.List[Quiz]:
    """
    Search for quizzes based on various filters and a full-text search query.

    :param session: The database session.
    :param query: The full-text search query.
    :param created_by_id: Filter quizzes created by a specific account.
    :param difficulty: Filter quizzes by difficulty levels.
    :param title: Filter quizzes by exact title.
    :param duration_gte: Filter quizzes with duration greater than or equal to this value.
    :param duration_lte: Filter quizzes with duration less than or equal to this value.
    :param created_at_gte: Filter quizzes created after this datetime.
    :param created_at_lte: Filter quizzes created before this datetime.
    :param updated_at_gte: Filter quizzes updated after this datetime.
    :param updated_at_lte: Filter quizzes updated before this datetime.
    :param limit: The maximum number of quizzes to return.
    :param offset: The number of quizzes to skip.
    :param exclude: A list of quiz IDs or UIDs to exclude from the search results.
    :param ordering: A list of SQLAlchemy ordering expressions to apply to the query.
    :param filters: Additional filters to apply to the query.
    :return: A list of quizzes matching the search criteria.
    """
    query_filters = [~Quiz.is_deleted]

    if query:
        tsquery = text_to_tsquery(query)
        query_filters.append(Quiz.search_tsvector.op("@@")(tsquery))
        # Update ordering to rank by relevance
        ordering = (
            sa.desc(func.ts_rank_cd(Quiz.search_tsvector, tsquery)),
            *ordering,
        )

    if created_by_id:
        query_filters.append(Quiz.created_by_id == created_by_id)

    if difficulty:
        query_filters.append(Quiz.difficulty.in_(difficulty))

    if title:
        query_filters.append(Quiz.title.ilike(f"%{title}%"))

    if duration_gte is not None:
        query_filters.append(Quiz.duration >= duration_gte)

    if duration_lte is not None:
        query_filters.append(Quiz.duration <= duration_lte)

    if created_at_gte:
        query_filters.append(Quiz.created_at >= created_at_gte)

    if created_at_lte:
        query_filters.append(Quiz.created_at <= created_at_lte)

    if updated_at_gte:
        query_filters.append(Quiz.updated_at >= updated_at_gte)

    if updated_at_lte:
        query_filters.append(Quiz.updated_at <= updated_at_lte)

    if exclude:
        query_filters.append(sa.and_(~Quiz.uid.in_(exclude), ~Quiz.id.in_(exclude)))

    filter_set = {getattr(Quiz, k) == v for k, v in filters.items()}
    result = await session.execute(
        sa.select(Quiz)
        .where(*query_filters, *filter_set)
        .limit(limit)
        .offset(offset)
        .options(
            # selectinload(Quiz.questions.and_(~Question.is_deleted)),
            joinedload(Quiz.created_by.and_(~Account.is_deleted)),
        )
        .order_by(*ordering)
    )
    return list(result.scalars().all())


async def search_questions(
    session: AsyncSession,
    query: typing.Optional[str] = None,
    *,
    difficulty: typing.Optional[typing.List[str]] = None,
    related_topics: typing.Optional[typing.List[typing.Union[int, str]]] = None,
    related_terms: typing.Optional[typing.List[typing.Union[int, str]]] = None,
    in_quizzes: typing.Optional[typing.List[typing.Union[int, str]]] = None,
    created_at_gte: typing.Optional[datetime.datetime] = None,
    created_at_lte: typing.Optional[datetime.datetime] = None,
    updated_at_gte: typing.Optional[datetime.datetime] = None,
    updated_at_lte: typing.Optional[datetime.datetime] = None,
    limit: int = 100,
    offset: int = 0,
    exclude: typing.Optional[typing.List[typing.Union[str, int]]] = None,
    ordering: typing.Sequence[sa.UnaryExpression] = Question.DEFAULT_ORDERING,
    **filters,
) -> typing.List[Question]:
    """
    Search for questions based on various filters and a full-text search query.

    :param session: The database session.
    :param query: The full-text search query.
    :param difficulty: Filter questions by difficulty levels.
    :param related_topics: Filter questions associated with specific topic IDs.
    :param related_terms: Filter questions associated with specific term IDs.
    :param in_quizzes: Filter questions belonging to specific quiz IDs.
    :param created_at_gte: Filter questions created after this datetime.
    :param created_at_lte: Filter questions created before this datetime.
    :param updated_at_gte: Filter questions updated after this datetime.
    :param updated_at_lte: Filter questions updated before this datetime.
    :param limit: The maximum number of questions to return.
    :param offset: The number of questions to skip.
    :param exclude: A list of question IDs or UIDs to exclude from the search results.
    :param ordering: A list of SQLAlchemy ordering expressions to apply to the query.
    :param filters: Additional filters to apply to the query.
    :return: A list of questions matching the search criteria.
    """
    query_filters = [~Question.is_deleted]

    if query:
        tsquery = text_to_tsquery(query)
        query_filters.append(Question.search_tsvector.op("@@")(tsquery))
        # Update ordering to rank by relevance
        ordering = (
            sa.desc(func.ts_rank_cd(Question.search_tsvector, tsquery)),
            *ordering,
        )

    if difficulty:
        query_filters.append(Question.difficulty.in_(difficulty))

    if created_at_gte:
        query_filters.append(Question.created_at >= created_at_gte)

    if created_at_lte:
        query_filters.append(Question.created_at <= created_at_lte)

    if updated_at_gte:
        query_filters.append(Question.updated_at >= updated_at_gte)

    if updated_at_lte:
        query_filters.append(Question.updated_at <= updated_at_lte)

    if related_topics:
        query_filters.append(
            Question.related_topics.any(
                sa.and_(
                    sa.or_(Topic.id.in_(related_topics), Topic.uid.in_(related_topics)),
                    ~Topic.is_deleted,
                )
            )
        )

    if related_terms:
        query_filters.append(
            Question.related_terms.any(
                sa.and_(
                    sa.or_(Term.id.in_(related_terms), Term.uid.in_(related_terms)),
                    ~Term.is_deleted,
                )
            )
        )

    if in_quizzes:
        query_filters.append(
            Question.quizzes.any(
                sa.and_(
                    sa.or_(Quiz.id.in_(in_quizzes), Quiz.uid.in_(in_quizzes)),
                    ~Quiz.is_deleted,
                )
            )
        )

    if exclude:
        query_filters.append(
            sa.and_(~Question.uid.in_(exclude), ~Question.id.in_(exclude))
        )

    filter_set = {getattr(Question, k) == v for k, v in filters.items()}
    result = await session.execute(
        sa.select(Question)
        .where(*query_filters, *filter_set)
        .limit(limit)
        .offset(offset)
        # .options(
        #     selectinload(Question.related_topics.and_(~Topic.is_deleted)),
        #     selectinload(Question.related_terms.and_(~Term.is_deleted)),
        # )
        .order_by(*ordering)
    )
    return list(result.scalars().all())


async def create_quiz_attempt(
    session: AsyncSession,
    quiz_id: int,
    attempted_by_id: uuid.UUID,
    **kwargs: typing.Any,
) -> QuizAttempt:
    """
    Create a quiz attempt.

    :param session: The database session.
    :param quiz_id: The ID of the quiz being attempted.
    :param attempted_by_id: The ID of the account attempting the quiz.
    :param kwargs: Additional attributes for the quiz attempt.
    :return: The created QuizAttempt object.
    """
    quiz_attempt = QuizAttempt(
        quiz_id=quiz_id,  # type: ignore[assignment]
        attempted_by_id=attempted_by_id,  # type: ignore[assignment]
        **kwargs,
    )
    session.add(quiz_attempt)
    return quiz_attempt


async def retrieve_quiz_attempt_by_uid(
    session: AsyncSession,
    quiz_attempt_uid: str,
) -> typing.Optional[QuizAttempt]:
    """
    Retrieve a quiz attempt by its UID.

    :param session: The database session.
    :param quiz_attempt_uid: The UID of the quiz attempt to retrieve.
    :return: The QuizAttempt object if found, otherwise None.
    """
    result = await session.execute(
        sa.select(QuizAttempt)
        .filter(QuizAttempt.uid == quiz_attempt_uid)
        .options(
            joinedload(QuizAttempt.quiz.and_(~Quiz.is_deleted)),
            joinedload(QuizAttempt.attempted_by.and_(~Account.is_deleted)),
            selectinload(QuizAttempt.question_answers),
        )
    )
    return result.scalar_one_or_none()


async def retrieve_quiz_attempts(
    session: AsyncSession,
    quiz_uid: str,
    limit: int = 50,
    offset: int = 0,
    ordering: typing.Sequence[sa.UnaryExpression] = QuizAttempt.DEFAULT_ORDERING,
    for_update: bool = False,
    **filters,
) -> typing.List[QuizAttempt]:
    """
    Retrieve quiz attempts for a specific quiz.

    :param session: The database session.
    :param quiz_uid: The UID of the quiz.
    :param limit: The maximum number of attempts to retrieve.
    :param offset: The number of attempts to skip.
    :param ordering: The ordering criteria for the results.
    :param filters: Additional filters to apply to the query.
    :return: A list of QuizAttempt objects.
    """
    filter_set = {getattr(QuizAttempt, k) == v for k, v in filters.items()}
    query = (
        sa.select(QuizAttempt)
        .join(QuizAttempt.quiz.and_(~Quiz.is_deleted))
        .where(Quiz.uid == quiz_uid, *filter_set)
        .limit(limit)
        .offset(offset)
        .order_by(*ordering)
        .options(
            joinedload(QuizAttempt.quiz.and_(~Quiz.is_deleted)),
            selectinload(QuizAttempt.question_answers),
            joinedload(QuizAttempt.attempted_by.and_(~Account.is_deleted)),
        )
    )
    if for_update:
        query = query.with_for_update(nowait=True, read=True)

    result = await session.execute(query)
    return list(result.scalars().all())


async def retrieve_quiz_attempt_and_question(
    session: AsyncSession,
    quiz_uid: str,
    question_uid: str,
    **filters,
) -> typing.Tuple[typing.Optional[QuizAttempt], typing.Optional[Question]]:
    """
    Retrieve a quiz attempt and the associated question with the given filters.

    :param session: The database session.
    :param quiz_uid: The UID of the quiz.
    :param question_uid: The UID of the question.
    :param filters: Additional filters to apply to the query.
    :return: A tuple of QuizAttempt and Question objects if found, otherwise None.
    """
    filter_set = {getattr(QuizAttempt, k) == v for k, v in filters.items()}
    result = await session.execute(
        sa.select(QuizAttempt, Question)
        .join(QuizAttempt.quiz.and_(~Quiz.is_deleted))
        .where(
            Quiz.uid == quiz_uid,
            sa.and_(Question.uid == question_uid, ~Question.is_deleted),
            *filter_set,
        )
        .options(
            joinedload(QuizAttempt.quiz.and_(~Quiz.is_deleted)),
            joinedload(QuizAttempt.attempted_by.and_(~Account.is_deleted)),
            selectinload(QuizAttempt.question_answers),
        )
    )
    return result.scalars().first() or (None, None)


async def retrieve_quiz_attempt_question_answer(
    session: AsyncSession,
    quiz_attempt_id: int,
    question_id: int,
    for_update: bool = False,
    **filters,
) -> typing.Optional[QuizAttemptQuestionAnswer]:
    """
    Retrieve a quiz attempt question answer.

    :param session: The database session.
    :param quiz_attempt_id: The ID of the quiz attempt.
    :param question_id: The ID of the question.
    :param for_update: Whether to lock the row for update.
    :param filters: Additional filters to apply to the query.
    :return: The QuizAttemptQuestionAnswer object if found, otherwise None.
    """
    filter_set = {
        getattr(QuizAttemptQuestionAnswer, k) == v for k, v in filters.items()
    }
    query = sa.select(QuizAttemptQuestionAnswer).where(
        QuizAttemptQuestionAnswer.quiz_attempt_id == quiz_attempt_id,
        QuizAttemptQuestionAnswer.question_id == question_id,
        *filter_set,
    )
    if for_update:
        query = query.with_for_update(nowait=True, read=True)

    result = await session.execute(query)
    return result.scalars().first()


async def create_quiz_attempt_question_answer(
    session: AsyncSession,
    quiz_attempt_id: int,
    question_id: int,
    **kwargs: typing.Any,
) -> QuizAttemptQuestionAnswer:
    """
    Create a quiz attempt question answer.

    :param session: The database session.
    :param quiz_attempt_id: The ID of the quiz attempt.
    :param question_id: The ID of the question.
    :param kwargs: Additional attributes for the quiz attempt question answer.
    :return: The created QuizAttemptQuestionAnswer object.
    """
    quiz_attempt_question_answer = QuizAttemptQuestionAnswer(
        quiz_attempt_id=quiz_attempt_id,  # type: ignore[assignment]
        question_id=question_id,  # type: ignore[assignment]
        **kwargs,
    )
    session.add(quiz_attempt_question_answer)
    return quiz_attempt_question_answer

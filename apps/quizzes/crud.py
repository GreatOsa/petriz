import typing
import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy as sa
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import func
from apps.accounts.models import Account
from apps.quizzes.models import (
    Quiz,
    Question,
    QuizAttempt,
    QuizAttemptQuestionAnswer,
    QuestionToQuizAssociation,
)
from apps.search.models import Topic, Term
from helpers.fastapi.sqlalchemy.utils import text_to_tsquery
from helpers.fastapi.utils import timezone


def sort_id_uids(
    ids: typing.Optional[typing.List[typing.Union[int, str]]],
) -> typing.Tuple[typing.List[int], typing.List[str]]:
    """
    Sort integers IDs and string UIDs into separate lists.

    :param ids: A list of IDs or UIDs.
    :return: A tuple of two lists: one for IDs and one for UIDs.
    """
    ids_list, uids_list = [], []
    if ids:
        for item in ids:
            if isinstance(item, int):
                ids_list.append(item)
            elif isinstance(item, str):
                uids_list.append(item)
    return ids_list, uids_list


async def retrieve_question_by_uid(
    session: AsyncSession,
    uid: str,
    version: typing.Optional[int] = None,
    for_update: bool = False,
) -> typing.Optional[Question]:
    """
    Retrieve a question by its UID.

    :param session: The database session.
    :param uid: The UID of the question to retrieve.
    :param version: The version of the question to retrieve. If None, the latest version is retrieved.
    :param for_update: Whether to lock the row for update but still allow reading.
    :return: The question object if found, otherwise None.
    """
    query = (
        sa.select(Question)
        .where(Question.uid == uid, ~Question.is_deleted)
        .options(
            joinedload(Question.created_by.and_(~Account.is_deleted)),
            joinedload(Question.deleted_by.and_(~Account.is_deleted)),
            selectinload(Question.related_topics.and_(~Topic.is_deleted)),
            selectinload(Question.related_terms.and_(~Term.is_deleted)),
        )
    )
    if version is not None:
        query = query.where(Question.version == version)
    else:
        query = query.where(Question.is_latest.is_(True))

    if for_update:
        query = query.with_for_update(
            of=Question.__table__,  # type: ignore
            nowait=True,
            read=True,
        )
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def retrieve_quiz_by_uid(
    session: AsyncSession,
    uid: str,
    version: typing.Optional[int] = None,
    for_update: bool = False,
) -> typing.Optional[Quiz]:
    """
    Retrieve a quiz by its UID.

    :param session: The database session.
    :param uid: The UID of the quiz to retrieve.
    :param version: The version of the quiz to retrieve. If None, the latest version is retrieved.
    :param for_update: Whether to lock the row for update but still allow reading.
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
            joinedload(Quiz.deleted_by.and_(~Account.is_deleted)),
            selectinload(Quiz.questions.and_(~Question.is_deleted)),
        )
    )
    if version is not None:
        query = query.where(Quiz.version == version)
    else:
        query = query.where(Quiz.is_latest.is_(True))

    if for_update:
        query = query.with_for_update(
            of=Quiz.__table__,  # type: ignore
            nowait=True,
            read=True,
        )

    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_quiz(session: AsyncSession, **create_kwargs) -> Quiz:
    quiz = Quiz(**create_kwargs)
    session.add(quiz)
    return quiz


async def check_quiz_has_attempts(
    session: AsyncSession,
    quiz_uid: str,
    version: typing.Optional[int] = None,
) -> bool:
    """
    Check if a specific/latest version of quiz has been attempted at all.

    This is used to determine if a quiz can be updated in-place safely,
    or a new version should be created.

    :param session: The database session.
    :param quiz_uid: The UID of the question to check.
    :return: True if the question has attempts, False otherwise.
    """
    query = (
        sa.select(QuizAttempt)
        .join(QuizAttempt.quiz.and_(~Quiz.is_deleted))
        .where(Quiz.uid == quiz_uid)
        .limit(1)
    )
    if version is not None:
        query = query.where(Quiz.version == version)
    else:
        query = query.where(Quiz.is_latest.is_(True))

    result = await session.execute(query)
    return result.scalars().first() is not None


async def copy_quiz(
    quiz: Quiz,
    **updated_attrs,
) -> Quiz:
    new_quiz = Quiz(
        **{
            "uid": quiz.uid,
            "title": quiz.title,
            "description": quiz.description,
            "created_by_id": quiz.created_by_id,
            "difficulty": quiz.difficulty,
            "duration": quiz.duration,
            "search_tsvector": quiz.search_tsvector,
            "questions": quiz.questions,
            "is_public": quiz.is_public,
            "is_deleted": quiz.is_deleted,
            "extradata": quiz.extradata,
            **updated_attrs,
        }
    )
    return new_quiz


async def delete_quiz_by_uid(
    session: AsyncSession,
    uid: str,
    deleted_by_id: typing.Optional[uuid.UUID] = None,
    exclude_versions: typing.Optional[typing.Sequence[int]] = None,
) -> bool:
    """
    Soft delete all versions of a quiz by its UID.

    :param session: The database session.
    :param uid: The UID of the quiz to delete.
    :param deleted_by_id: The ID of the account performing the deletion.
    :param exclude_versions: Versions of the quiz to not delete.
    :return: True if the quiz was deleted, otherwise False.
    """
    query = (
        sa.update(Quiz)
        .where(Quiz.uid == uid, ~Quiz.is_deleted)
        .values(
            is_deleted=True,
            deleted_by_id=deleted_by_id,
            deleted_at=timezone.now(),
        )
    )
    if exclude_versions:
        query = query.where(~Quiz.version.in_(exclude_versions))
    result = await session.execute(query.returning(sa.func.count(Quiz.id)))
    return result.scalar_one() > 0


async def create_question(session: AsyncSession, **create_kwargs) -> Question:
    question = Question(**create_kwargs)
    session.add(question)
    return question


async def check_question_has_attempts(
    session: AsyncSession,
    question_uid: str,
    version: typing.Optional[int] = None,
) -> bool:
    """
    Check if a specific/latest version of question has been answered in any quiz attempts.

    This is used to determine if a question can be updated in-place safely,
    or a new version should be created.

    :param session: The database session.
    :param question_uid: The UID of the question to check.
    :return: True if the question has attempts, False otherwise.
    """
    query = (
        sa.select(QuizAttemptQuestionAnswer)
        .join(QuizAttemptQuestionAnswer.question.and_(~Question.is_deleted))
        .where(Question.uid == question_uid)
        .limit(1)
    )
    if version is not None:
        query = query.where(Question.version == version)
    else:
        query = query.where(Question.is_latest.is_(True))

    result = await session.execute(query)
    return result.scalars().first() is not None


async def copy_question(
    question: Question,
    **updated_attrs,
) -> Question:
    return Question(
        **{
            "uid": question.uid,
            "question": question.question,
            "options": question.options,
            "difficulty": question.difficulty,
            "correct_option_index": question.correct_option_index,
            "hint": question.hint,
            "search_tsvector": question.search_tsvector,
            "related_topics": question.related_topics,
            "related_terms": question.related_terms,
            **updated_attrs,
        }
    )


async def create_updated_question(
    session: AsyncSession, question: Question, **update_kwargs
) -> Question:
    new_question = await copy_question(question, **update_kwargs)
    session.add(new_question)
    return new_question


async def bulk_create_questions(
    session: AsyncSession, questions: typing.Sequence[Question]
) -> typing.Sequence[Question]:
    session.add_all(questions)
    await session.flush()
    return questions


async def delete_question_by_uid(
    session: AsyncSession,
    uid: str,
    deleted_by_id: typing.Optional[uuid.UUID] = None,
    exclude_versions: typing.Optional[typing.Sequence[int]] = None,
) -> bool:
    """
    Soft delete all versions of a question by its UID.

    :param session: The database session.
    :param uid: The UID of the question to delete.
    :param deleted_by_id: The ID of the account performing the deletion.
    :param exclude_versions: Versions of the question to not delete.
    :return: True if the question was deleted, otherwise False.
    """
    query = (
        sa.update(Question)
        .where(Question.uid == uid, ~Question.is_deleted)
        .values(
            is_deleted=True,
            deleted_by_id=deleted_by_id,
            deleted_at=timezone.now(),
        )
    )
    if exclude_versions:
        query = query.where(~Question.version.in_(exclude_versions))
    result = await session.execute(query.returning(sa.func.count(Question.id)))
    return result.scalar_one() > 0


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
    version: typing.Optional[int] = None,
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
    :param version: The version of the quiz to filter by.
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
        excluded_ids, excluded_uids = sort_id_uids(exclude)
        if not excluded_ids and not excluded_uids:
            raise ValueError("At least one ID or UID must be provided for exclusion.")
        query_filters.append(~Quiz.uid.in_(excluded_uids) & ~Quiz.id.in_(excluded_ids))

    if version is not None and not filters.get("is_latest", False):
        query_filters.append(Quiz.version == version)

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
    version: typing.Optional[int] = None,
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
    :param version: The version of the question to filter by.
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
        related_topics_ids, related_topics_uids = sort_id_uids(related_topics)
        if not related_topics_ids and not related_topics_uids:
            raise ValueError(
                "At least one ID or UID must be provided for related topics."
            )
        query_filters.append(
            Question.related_topics.any(
                (Topic.id.in_(related_topics_ids) | Topic.uid.in_(related_topics_uids))
                & ~Topic.is_deleted,
            )
        )

    if related_terms:
        related_terms_ids, related_terms_uids = sort_id_uids(related_terms)
        if not related_terms_ids and not related_terms_uids:
            raise ValueError(
                "At least one ID or UID must be provided for related terms."
            )
        query_filters.append(
            Question.related_terms.any(
                (Term.id.in_(related_terms_ids) | Term.uid.in_(related_terms_uids))
                & ~Term.is_deleted,
            )
        )

    if in_quizzes:
        quiz_ids, quiz_uids = sort_id_uids(in_quizzes)
        if not quiz_ids and not quiz_uids:
            raise ValueError("At least one ID or UID must be provided for inclusion.")
        query_filters.append(
            Question.quizzes.any(
                (Quiz.id.in_(quiz_ids) | Quiz.uid.in_(quiz_uids)) & ~Quiz.is_deleted
            )
        )

    if exclude:
        excluded_ids, excluded_uids = sort_id_uids(exclude)
        if not excluded_ids and not excluded_uids:
            raise ValueError("At least one ID or UID must be provided for exclusion.")
        query_filters.append(
            ~Question.uid.in_(excluded_uids) & ~Question.id.in_(excluded_ids)
        )

    if version is not None and not filters.get("is_latest", False):
        query_filters.append(Question.version == version)

    filter_set = {getattr(Question, k) == v for k, v in filters.items()}
    result = await session.execute(
        sa.select(Question)
        .where(*query_filters, *filter_set)
        .limit(limit)
        .offset(offset)
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
        query = query.with_for_update(
            of=QuizAttempt.__table__,  # type: ignore
            nowait=True,
            read=True,
        )

    result = await session.execute(query)
    return list(result.scalars().all())


async def retrieve_question_in_quiz(
    session: AsyncSession,
    question_uid: str,
    quiz_id: int,
    **filters,
) -> typing.Optional[Question]:
    """
    Retrieve the specific version of a question (identified by the given UID), 
    that is in/associated with a specific version of a quiz 
    (identified by the given quiz ID).

    :param session: The database session.
    :param quiz_id: The ID of the quiz.
    :param question_uid: The UID of the question.
    :param filters: Additional filters to apply to the query.
    :return: The Question object if found, otherwise None.
    """
    filter_set = {getattr(Question, k) == v for k, v in filters.items()}
    result = await session.execute(
        sa.select(Question)
        .join(
            QuestionToQuizAssociation,
            QuestionToQuizAssociation.question_id == Question.id,
        )
        .where(
            Question.uid == question_uid,
            QuestionToQuizAssociation.quiz_id == quiz_id,
            ~Question.is_deleted,
            *filter_set,
        )
    )
    return result.scalars().first()


async def retrieve_quiz_attempt_question_answer(
    session: AsyncSession,
    quiz_attempt_id: int,
    question_id: int,
    for_update: bool = False,
    **filters,
) -> typing.Optional[QuizAttemptQuestionAnswer]:
    """
    Retrieve a quiz attempt question answer by its quiz attempt ID and question ID.

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
        query = query.with_for_update(
            of=QuizAttemptQuestionAnswer.__table__,  # type: ignore
            nowait=True,
            read=True,
        )

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

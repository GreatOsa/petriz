import typing
from annotated_types import Le, MaxLen, MinLen
import fastapi
import pydantic
from sqlalchemy.exc import OperationalError
from fastapi_cache.decorator import cache

from helpers.fastapi import response
from helpers.fastapi.dependencies.access_control import ActiveUser
from api.dependencies.auditing import event
from api.dependencies.authentication import (
    authentication_required,
    authenticate_connection,
)
from api.dependencies.authorization import permissions_required
from helpers.fastapi.exceptions import capture
from helpers.fastapi.utils import timezone
from helpers.generics.utils import merge_mappings
from helpers.fastapi.dependencies.connections import AsyncDBSession, User
from helpers.fastapi.response.pagination import paginated_data
from helpers.fastapi.requests.query import Limit, Offset, clean_params

from . import crud, schemas
from .models import Question
from .query import (
    SearchQuery,
    QuizTitle,
    QuizDifficulty,
    QuestionDifficulty,
    QuizDurationGte,
    QuizDurationLte,
    QuizOrdering,
    QuestionOrdering,
    QuizIsPublic,
    OnlyPrivateQuizzes,
    CreatedAtGte,
    CreatedAtLte,
    UpdatedAtGte,
    UpdatedAtLte,
    QuizUIDs,
)
from apps.search.query import Terms, Topics
from apps.search.crud import (
    retrieve_topics_by_name_or_uid,
    retrieve_terms_by_name_or_uid,
)
from apps.accounts.models import Account


router = fastapi.APIRouter(
    dependencies=[
        event(
            "quizzes_access",
            description="Access quiz endpoints.",
        ),
        permissions_required(
            "quizzes::*::*",
            "questions::*::*",
        ),
    ]
)


QuizUID: typing.TypeAlias = typing.Annotated[
    pydantic.StrictStr,
    fastapi.Path(
        title="Quiz UID",
        description="Unique identifier for the quiz",
        max_length=50,
    ),
]
QuizAttemptUID: typing.TypeAlias = typing.Annotated[
    pydantic.StrictStr,
    fastapi.Path(
        title="Quiz attempt UID",
        description="Unique identifier for the quiz attempt",
        max_length=50,
    ),
]
QuestionUID: typing.TypeAlias = typing.Annotated[
    pydantic.StrictStr,
    fastapi.Path(
        title="Question UID",
        description="Unique identifier for the question",
        max_length=50,
    ),
]


@router.post(
    "/",
    dependencies=[
        event(
            "quiz_create",
            target="quizzes",
            description="Create a new quiz.",
        ),
        permissions_required(
            "quizzes::*::create",
        ),
        authenticate_connection,
    ],
    description="Create a new quiz",
)
async def create_quiz(
    data: schemas.QuizCreateSchema,
    session: AsyncDBSession,
    user: User[Account],
):
    dumped_data = data.model_dump()
    questions = [
        Question(**question_data) for question_data in dumped_data.pop("questions", [])
    ]
    dumped_data["questions"] = questions
    if not user or not user.is_authenticated:
        dumped_data["is_public"] = True

    quiz = await crud.create_quiz(session, created_by=user, **dumped_data)
    await session.commit()
    await session.refresh(quiz, attribute_names=["created_by", "questions"])
    return response.created(
        "Quiz created", data=schemas.QuizSchema.model_validate(quiz)
    )


@router.get(
    "/",
    dependencies=[
        event(
            "quizzes_list",
            target="quizzes",
            description="Retrieve quizzes.",
        ),
        permissions_required(
            "quizzes::*::list",
        ),
        authenticate_connection,
    ],
    description="Retrieve a list of quizzes",
)
@cache(namespace="quizzes")
async def retrieve_quizzes(
    request: fastapi.Request,
    session: AsyncDBSession,
    user: User[Account],
    query: SearchQuery,
    title: QuizTitle,
    difficulty: QuizDifficulty,
    duration_gte: QuizDurationGte,
    duration_lte: QuizDurationLte,
    created_at_gte: CreatedAtGte,
    created_at_lte: CreatedAtLte,
    updated_at_gte: UpdatedAtGte,
    updated_at_lte: UpdatedAtLte,
    is_public: QuizIsPublic,
    private_only: OnlyPrivateQuizzes,
    ordering: QuizOrdering,
    limit: typing.Annotated[Limit, Le(50)] = 50,
    offset: Offset = 0,
):
    filters = clean_params(
        query=query,
        title=title,
        difficulty=difficulty,
        duration_gte=duration_gte,
        duration_lte=duration_lte,
        created_at_gte=created_at_gte,
        created_at_lte=created_at_lte,
        updated_at_gte=updated_at_gte,
        updated_at_lte=updated_at_lte,
        is_public=is_public,
        ordering=ordering,
        limit=limit,
        offset=offset,
    )
    if user and user.is_authenticated and private_only:
        filters["created_by_id"] = user.id

    quizzes = await crud.search_quizzes(session, **filters)
    response_data = [schemas.BaseQuizSchema.model_validate(quiz) for quiz in quizzes]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/questions",
    dependencies=[
        event(
            "quiz_questions_list",
            target="quiz_questions",
            description="Retrieve/search quiz questions based on various filters.",
        ),
        permissions_required(
            "questions::*::list",
        ),
        authenticate_connection,
    ],
    description="Retrieve or search a list of quiz questions based on various filters.",
)
@cache(namespace="quiz_questions")
async def retrieve_quiz_questions(
    request: fastapi.Request,
    session: AsyncDBSession,
    # user: User[Account],
    query: SearchQuery,
    difficulty: QuestionDifficulty,
    quiz_uids: QuizUIDs,
    related_terms: Terms,
    related_topics: Topics,
    created_at_gte: CreatedAtGte,
    created_at_lte: CreatedAtLte,
    updated_at_gte: UpdatedAtGte,
    updated_at_lte: UpdatedAtLte,
    ordering: QuestionOrdering,
    limit: typing.Annotated[Limit, Le(50)] = 50,
    offset: Offset = 0,
):
    filters = clean_params(
        query=query,
        difficulty=difficulty,
        in_quizzes=quiz_uids,
        created_at_gte=created_at_gte,
        created_at_lte=created_at_lte,
        updated_at_gte=updated_at_gte,
        updated_at_lte=updated_at_lte,
        ordering=ordering,
        limit=limit,
        offset=offset,
    )
    if related_terms:
        terms = await retrieve_terms_by_name_or_uid(session, related_terms)
        filters["related_terms"] = {term.uid: term for term in terms if term}

    if related_topics:
        topics = await retrieve_topics_by_name_or_uid(session, related_topics)
        filters["related_topics"] = {topic.uid: topic for topic in topics if topic}

    questions = await crud.search_questions(session, **filters)
    response_data = [
        schemas.BaseQuestionSchema.model_validate(question) for question in questions
    ]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{quiz_uid}",
    dependencies=[
        event(
            "quiz_retrieve",
            target="quizzes",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Retrieve a quiz.",
        ),
        permissions_required(
            "quizzes::*::view",
        ),
        authenticate_connection,
    ],
    description="Retrieve a quiz",
)
@cache(namespace="quizzes")
async def retrieve_quiz(
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: User[Account],
):
    quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid)
    if not quiz or (not quiz.is_public and quiz.created_by != user):
        return response.notfound("Quiz not found")
    return response.success(data=schemas.QuizSchema.model_validate(quiz))


@router.patch(
    "/{quiz_uid}",
    dependencies=[
        event(
            "quiz_update",
            target="quizzes",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Update a quiz.",
        ),
        permissions_required(
            "quizzes::*::update",
        ),
        authentication_required,
    ],
    description="Update a quiz",
)
async def update_quiz(
    quiz_uid: QuizUID,
    data: schemas.QuizUpdateSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Cannot update quiz due to conflict",
    ):
        quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid, for_update=True)

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    dumped_data = data.model_dump(exclude_unset=True)
    for key, value in dumped_data.items():
        if key == "data":
            value = merge_mappings(quiz.data, value)
        setattr(quiz, key, value)

    session.add(quiz)
    await session.commit()
    await session.refresh(quiz, attribute_names=["created_by", "questions"])
    return response.success(
        "Quiz updated", data=schemas.QuizSchema.model_validate(quiz)
    )


@router.put(
    "/{quiz_uid}/questions",
    dependencies=[
        event(
            "quiz_questions_add",
            target="quiz_questions",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Add/update quiz questions.",
        ),
        permissions_required(
            "quizzes::*::update",
            "questions::*::update",
        ),
        authentication_required,
    ],
    description="Add new quiz questions by sending a list of the questions' data or UIDs.",
)
async def add_quiz_questions(
    quiz_uid: QuizUID,
    data: typing.Annotated[
        typing.List[typing.Union[schemas.QuestionCreateSchema, pydantic.StrictStr]],
        MaxLen(1000),
        MinLen(1),
    ],
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Cannot update quiz due to conflict",
    ):
        quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid, for_update=True)

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    async with session.begin_nested():
        for question_data in data:
            if isinstance(question_data, str):
                question = await crud.retrieve_question_by_uid(session, question_data)
                if not question:
                    return response.notfound(
                        f"Question with uid '{question_data}' not found"
                    )
            else:
                question = await crud.create_question(
                    session, **question_data.model_dump()
                )
            quiz.questions.add(question)

        session.add(quiz)
        await session.commit()
    await session.refresh(quiz, attribute_names=["created_by", "questions"])
    return response.success(
        "Quiz questions updated", data=schemas.QuizSchema.model_validate(quiz)
    )


@router.delete(
    "/{quiz_uid}/questions",
    dependencies=[
        event(
            "quiz_questions_remove",
            target="quiz_questions",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Remove quiz questions.",
        ),
        permissions_required(
            "quizzes::*::update",
            "questions::*::delete",
        ),
        authentication_required,
    ],
    description="Remove quiz questions by their UIDs. Send a list of question UIDs to remove.",
)
async def remove_quiz_questions(
    quiz_uid: QuizUID,
    data: typing.Annotated[
        typing.List[pydantic.StrictStr],
        MaxLen(1000),
        MinLen(1),
    ],
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Cannot update quiz due to conflict",
    ):
        quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid, for_update=True)

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    for question_uid in data:
        question = await crud.retrieve_question_by_uid(session, question_uid)
        if not question:
            return response.notfound(f"Question with uid '{question_uid}' not found")
        quiz.questions.remove(question)

    session.add(quiz)
    await session.commit()
    await session.refresh(quiz, attribute_names=["created_by", "questions"])
    return response.success(
        "Quiz questions removed", data=schemas.QuizSchema.model_validate(quiz)
    )


@router.delete(
    "/{quiz_uid}",
    dependencies=[
        event(
            "quiz_delete",
            target="quizzes",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Delete a quiz.",
        ),
        permissions_required(
            "quizzes::*::delete",
        ),
        authentication_required,
    ],
    description="Delete a quiz",
)
async def delete_quiz(
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Cannot delete quiz due to conflict",
    ):
        quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid, for_update=True)

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    # For now do not delete the quiz but clear the created_by
    # and make it public
    quiz.created_by_id = None
    quiz.is_public = True
    session.add(quiz)
    await session.commit()
    return response.success("Quiz deleted")


@router.post(
    "/{quiz_uid}/attempts",
    dependencies=[
        event(
            "quiz_attempt_create",
            target="quizzes",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Create a quiz attempt.",
        ),
        permissions_required(
            "quizzes::*::attempt",
        ),
        authentication_required,
    ],
    description="Create a quiz attempt",
)
async def create_quiz_attempt(
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid)
    if not quiz or (not quiz.is_public and not quiz.created_by == user):
        return response.notfound("Quiz not found")

    attempt = await crud.create_quiz_attempt(
        session,
        attempted_by_id=user.id,
        quiz_id=quiz.id,
        duration=quiz.duration,
    )
    await session.commit()
    await session.refresh(
        attempt,
        attribute_names=[
            "quiz",
            "attempted_by",
            "question_answers",
        ],
    )
    return response.created(
        "Quiz attempt created", data=schemas.QuizAttemptSchema.model_validate(attempt)
    )


@router.get(
    "/{quiz_uid}/attempts",
    dependencies=[
        event(
            "quiz_attempts_list",
            target="quiz_attempts",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Retrieve quiz attempts.",
        ),
        permissions_required(
            "quizzes::*::attempt",
        ),
        authentication_required,
    ],
    description="Retrieve quiz attempts",
)
@cache(namespace="quiz_attempts", expire=60)
async def retrieve_quiz_attempts(
    request: fastapi.Request,
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
    ordering: QuestionOrdering,
    limit: typing.Annotated[Limit, Le(50)] = 50,
    offset: Offset = 0,
):
    filters = clean_params(
        ordering=ordering,
        limit=limit,
        offset=offset,
    )

    quiz = await crud.retrieve_quiz_by_uid(session, quiz_uid)
    if not quiz or (not quiz.is_public and not quiz.created_by == user):
        return response.notfound("Quiz not found")

    filters["quiz_uid"] = quiz.uid
    filters["attempted_by_id"] = user.id
    attempts = await crud.retrieve_quiz_attempts(session, **filters)
    response_data = [
        schemas.BaseQuizAttemptSchema.model_validate(attempt) for attempt in attempts
    ]
    return response.success(
        data=paginated_data(
            request,
            data=response_data,
            limit=limit,
            offset=offset,
        )
    )


@router.get(
    "/{quiz_uid}/attempts/{attempt_uid}",
    dependencies=[
        event(
            "quiz_attempt_retrieve",
            target="quiz_attempts",
            target_uid=fastapi.Path(
                alias="attempt_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Retrieve a quiz attempt.",
        ),
        permissions_required(
            "quizzes::*::attempt",
        ),
        authentication_required,
    ],
    description="Retrieve a quiz attempt",
)
@cache(namespace="quiz_attempts", expire=60)
async def retrieve_quiz_attempt(
    quiz_uid: QuizUID,
    attempt_uid: QuizAttemptUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    attempts = await crud.retrieve_quiz_attempts(
        session,
        quiz_uid=quiz_uid,
        uid=attempt_uid,
        attempted_by_id=user.id,
        limit=1,
    )
    if not attempts:
        return response.notfound("Quiz attempt not found")

    attempt = attempts[0]
    return response.success(data=schemas.QuizAttemptSchema.model_validate(attempt))


@router.put(
    "/{quiz_uid}/attempts/{attempt_uid}/question-answers/{question_uid}",
    dependencies=[
        event(
            "quiz_attempt_question_answer_upsert",
            target="quiz_attempts",
            target_uid=fastapi.Path(
                alias="attempt_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Create or update a quiz attempt question answer.",
        ),
        permissions_required(
            "quizzes::*::attempt",
        ),
        authentication_required,
    ],
    description="Create or update a quiz attempt question answer",
)
async def upsert_quiz_attempt_question_answer(
    quiz_uid: QuizUID,
    attempt_uid: QuizAttemptUID,
    question_uid: QuestionUID,
    data: schemas.QuizAttemptQuestionAnswerCreateSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    attempt, question = await crud.retrieve_quiz_attempt_and_question(
        session,
        quiz_uid=quiz_uid,
        uid=attempt_uid,
        question_uid=question_uid,
        attempted_by_id=user.id,
    )

    if not attempt:
        return response.notfound("Quiz attempt not found")
    if not question:
        return response.notfound(
            "Question not found. Are you sure it belongs to this quiz?"
        )

    if attempt.submitted:
        return response.unprocessable_entity("Quiz attempt already submitted")
    if attempt.is_expired:
        return response.unprocessable_entity("Quiz attempt duration elapsed")

    async with capture.capture(
        OperationalError,
        code=409,
        content="Answer could not be registered due to conflict.",
    ), session.begin_nested():
        question_answer = await crud.retrieve_quiz_attempt_question_answer(
            session,
            quiz_attempt_id=attempt.id,
            question_id=question.id,
            answered_by_id=user.id,
            for_update=True,
        )
        if not question_answer:
            question_answer = await crud.create_quiz_attempt_question_answer(
                session,
                quiz_id=attempt.quiz_id,
                quiz_attempt_id=attempt.id,
                question_id=question.id,
                answered_by_id=user.id,
                **data.model_dump(),
            )
        else:
            if question_answer.is_final:
                return response.conflict("Question answer has already been locked in.")

            dumped_data = data.model_dump(exclude_unset=True)
            for key, value in dumped_data.items():
                setattr(question_answer, key, value)

            if question_answer.is_final:
                question_answer.is_correct = (
                    question_answer.answer_index == question.correct_option_index
                )
            session.add(question_answer)

    await session.commit()
    await session.refresh(
        attempt,
        attribute_names=[
            "quiz",
            "score",
            "attempted_questions",
            "question_answers",
        ],
    )
    return response.success(
        "Quiz question answer updated!",
        data=schemas.QuizAttemptSchema.model_validate(attempt),
    )


@router.post(
    "/{quiz_uid}/attempts/{attempt_uid}/submit",
    dependencies=[
        event(
            "quiz_attempt_submit",
            target="quizzes",
            target_uid=fastapi.Path(
                alias="quiz_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Submit a quiz attempt.",
        ),
        permissions_required(
            "quizzes::*::attempt",
        ),
        authentication_required,
    ],
    description="Submit a quiz attempt",
)
async def submit_quiz_attempt(
    quiz_uid: QuizUID,
    attempt_uid: QuizAttemptUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Submission failed due to conflict.",
    ):
        attempts = await crud.retrieve_quiz_attempts(
            session,
            quiz_uid=quiz_uid,
            attempt_uid=attempt_uid,
            attempted_by_id=user.id,
            limit=1,
            for_update=True,
        )
    if not attempts:
        return response.notfound("Quiz attempt not found")

    attempt = attempts[0]
    if attempt.submitted:
        return response.conflict("Quiz attempt already submitted")
    if attempt.attempted_questions == 0:
        return response.unprocessable_entity("No questions attempted.")

    attempt.submitted = True
    attempt.submitted_at = timezone.now()
    session.add(attempt)
    await session.commit()
    return response.success(
        "Quiz attempt submitted",
        data=schemas.QuizAttemptSchema.model_validate(attempt),
    )


# TODO: Calculate quiz attempt score with background celery task

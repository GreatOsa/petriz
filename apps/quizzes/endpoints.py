import typing
from annotated_types import Le
import fastapi
import pydantic
from sqlalchemy.exc import OperationalError
from fastapi_cache.decorator import cache

from helpers.fastapi import response
from helpers.fastapi.dependencies.access_control import ActiveUser, staff_user_only
from helpers.fastapi.auditing.dependencies import event
from api.dependencies.authentication import (
    authentication_required,
    authenticate_connection,
)
from api.dependencies.authorization import (
    permissions_required,
    authorized_api_client_only,
)
from helpers.fastapi.exceptions import capture
from helpers.fastapi.utils import timezone
from helpers.generics.utils import merge_mappings
from helpers.fastapi.dependencies.connections import AsyncDBSession, User
from helpers.fastapi.response.pagination import paginated_data, PaginatedResponse
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
    QuizAttemptOrdering,
    QuizIsPublic,
    OnlyPrivateQuizzes,
    CreatedAtGte,
    CreatedAtLte,
    UpdatedAtGte,
    UpdatedAtLte,
    QuizUIDs,
    QuizVersion,
    QuestionVersion,
)
from .utils import guess_quiz_difficulty
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
        authorized_api_client_only,
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
    "/questions",
    dependencies=[
        event(
            "quiz_questions_create",
            target="quiz_questions",
            description="Create a new quiz question.",
        ),
        permissions_required(
            "questions::*::create",
        ),
        authentication_required,
        staff_user_only,
    ],
    description="Create a new quiz question",
    response_model=response.DataSchema[schemas.QuestionSchema],
    status_code=201,
)
async def create_quiz_question(
    data: schemas.QuestionCreateSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    dumped_data = data.model_dump(by_alias=True)
    question = await crud.create_question(
        session,
        is_latest=True,
        created_by_id=user.id,
        **dumped_data,
    )
    await session.commit()
    await session.refresh(
        question,
        attribute_names=[
            "created_by",
            "deleted_by",
            "related_terms",
            "related_topics",
        ],
    )
    return response.created(
        "Quiz question created",
        data=schemas.QuestionSchema.model_validate(question),
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
    ],
    description="Retrieve or search a list of quiz questions based on various filters.",
    response_model=PaginatedResponse[schemas.BaseQuestionSchema],  # type: ignore
    status_code=200,
)
@cache(namespace="quiz_questions")
async def retrieve_quiz_questions(
    request: fastapi.Request,
    session: AsyncDBSession,
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
        if terms:
            filters["related_terms"] = {term.uid: term for term in terms if term}

    if related_topics:
        topics = await retrieve_topics_by_name_or_uid(session, related_topics)
        if topics:
            filters["related_topics"] = {topic.uid: topic for topic in topics if topic}

    filters["is_latest"] = True
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
    "/questions/{question_uid}",
    dependencies=[
        event(
            "quiz_question_retrieve",
            target="quiz_questions",
            target_uid=fastapi.Path(
                alias="question_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Retrieve a quiz question.",
        ),
        permissions_required(
            "questions::*::view",
        ),
    ],
    description="Retrieve a specific/latest version of a quiz question",
    response_model=response.DataSchema[schemas.QuestionSchema],
    status_code=200,
)
@cache(namespace="quiz_questions")
async def retrieve_quiz_question(
    question_uid: QuestionUID,
    session: AsyncDBSession,
    version: QuestionVersion = None,
):
    question = await crud.retrieve_question_by_uid(
        session, uid=question_uid, version=version
    )
    if not question:
        return response.notfound("Quiz question not found")
    return response.success(data=schemas.QuestionSchema.model_validate(question))


@router.patch(
    "/questions/{question_uid}",
    dependencies=[
        event(
            "quiz_question_update",
            target="quiz_questions",
            target_uid=fastapi.Path(
                alias="question_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Update a quiz question.",
        ),
        permissions_required(
            "questions::*::update",
        ),
        authentication_required,
        staff_user_only,
    ],
    description="Update the latest version of a quiz question",
    response_model=response.DataSchema[schemas.QuestionSchema],
    status_code=200,
)
async def update_quiz_question(
    question_uid: QuestionUID,
    data: schemas.QuestionUpdateSchema,
    session: AsyncDBSession,
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Cannot update quiz question due to conflict",
    ):
        question = await crud.retrieve_question_by_uid(
            session,
            uid=question_uid,
            for_update=True,
        )
    if not question:
        return response.notfound("Quiz question not found")

    dumped_data = data.model_dump(exclude_unset=True)
    dumped_data["is_latest"] = True
    target_question = question
    has_been_attempted = await crud.check_question_has_attempts(session, question_uid)
    async with session.begin_nested():
        if has_been_attempted:
            new_question = await crud.create_updated_question(
                session, question, **dumped_data
            )
            target_question = new_question
            question.is_latest = False  # Mark as old
            session.add(question)
        else:
            for key, value in dumped_data.items():
                setattr(question, key, value)

        session.add(target_question)
        await session.commit()

    await session.refresh(
        target_question,
        attribute_names=[
            "version",
        ],
    )
    return response.success(
        "Quiz question updated",
        data=schemas.QuestionSchema.model_validate(question),
    )


@router.delete(
    "/questions/{question_uid}",
    dependencies=[
        event(
            "quiz_question_delete",
            target="quiz_questions",
            target_uid=fastapi.Path(
                alias="question_uid",
                alias_priority=1,
                include_in_schema=False,
            ),
            description="Delete a quiz question.",
        ),
        permissions_required(
            "questions::*::delete",
        ),
        authentication_required,
        staff_user_only,
    ],
    description="Delete all versions of a quiz question. Only, use when deleting is completely necessary.",
    response_model=response.DataSchema[None],
    status_code=200,
)
async def delete_quiz_question(
    question_uid: QuestionUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    deleted_questions = await crud.delete_question_by_uid(
        session,
        uid=question_uid,
        deleted_by_id=user.id,
    )
    if not deleted_questions:
        return response.notfound("Quiz question not found")

    await session.commit()
    return response.success("Quiz question deleted")


@router.post(
    "",
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
    response_model=response.DataSchema[schemas.QuizSchema],
    status_code=201,
)
async def create_quiz(
    data: schemas.QuizCreateSchema,
    session: AsyncDBSession,
    user: User[Account],
):
    dumped_data = data.model_dump(by_alias=True)
    questions = set()
    for question_data in dumped_data.pop("questions", []):
        if isinstance(question_data, str):
            question = await crud.retrieve_question_by_uid(session, question_data)
            if not question:
                continue
        else:
            question = Question(**question_data)
        questions.add(question)

    dumped_data["questions"] = questions
    if not user or not user.is_authenticated:
        dumped_data["is_public"] = True
    else:
        dumped_data["created_by_id"] = user.id
        dumped_data["is_public"] = False

    dumped_data["difficulty"] = guess_quiz_difficulty(questions).value  # type: ignore
    dumped_data["is_latest"] = True
    quiz = await crud.create_quiz(session, **dumped_data)
    await session.commit()
    await session.refresh(
        quiz,
        attribute_names=[
            "questions_count",
            "created_by",
            "deleted_by",
            "questions",
        ],
    )
    return response.created(
        "Quiz created", data=schemas.QuizSchema.model_validate(quiz)
    )


@router.get(
    "",
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
    response_model=PaginatedResponse[schemas.BaseQuizSchema],  # type: ignore
    status_code=200,
)
# @cache(namespace="quizzes")
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

    filters["is_latest"] = True
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
    description="Retrieve a specific/latest version of a quiz",
    response_model=response.DataSchema[schemas.QuizSchema],
    status_code=200,
)
@cache(namespace="quizzes")
async def retrieve_quiz(
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: User[Account],
    version: QuizVersion = None,
):
    quiz = await crud.retrieve_quiz_by_uid(
        session,
        uid=quiz_uid,
        version=version,
    )
    if not quiz or (
        not quiz.is_public and quiz.created_by != user and user and not user.is_staff
    ):
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
    description="Update the latest version of a quiz",
    response_model=response.DataSchema[schemas.QuizSchema],
    status_code=200,
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
        quiz = await crud.retrieve_quiz_by_uid(
            session,
            uid=quiz_uid,
            for_update=True,
        )

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    dumped_data = data.model_dump(exclude_unset=True)
    for key, value in dumped_data.items():
        if key in ["metadata", "extradata"]:
            if value is None:
                value = {}
            else:
                value = merge_mappings(quiz.metadata, value)
        setattr(quiz, key, value)

    session.add(quiz)
    await session.commit()
    await session.refresh(
        quiz,
        attribute_names=[
            "created_by",
            "deleted_by",
            "questions",
        ],
    )
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
    description="Add new quiz questions to the latest version of a quiz by sending a list of the questions' data or UIDs.",
    response_model=response.DataSchema[schemas.QuizSchema],
    status_code=200,
)
async def add_quiz_questions(
    quiz_uid: QuizUID,
    data: schemas.QuizQuestionAddSchema,
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

    new_questions = set()
    async with session.begin_nested():
        for question_data in data.questions:
            if isinstance(question_data, str):
                question = await crud.retrieve_question_by_uid(
                    session, uid=question_data
                )
                if not question:
                    return response.notfound(
                        f"Question with uid '{question_data}' not found"
                    )
            else:
                question = await crud.create_question(
                    session, **question_data.model_dump()
                )
            new_questions.add(question)

        target_quiz = quiz
        has_been_attempted = await crud.check_quiz_has_attempts(session, quiz_uid)
        if has_been_attempted:
            new_quiz = await crud.copy_quiz(quiz, is_latest=True)
            target_quiz = new_quiz
            new_quiz.questions |= new_questions
            quiz.is_latest = False
            session.add(quiz)
        else:
            quiz.questions |= new_questions

        target_quiz.difficulty = guess_quiz_difficulty(target_quiz.questions).value  # type: ignore
        session.add(target_quiz)
        await session.commit()

    await session.refresh(
        target_quiz,
        attribute_names=[
            "version",
            "questions_count",
            "created_by",
            "deleted_by",
            "questions",
        ],
    )
    return response.success(
        "Quiz questions updated", data=schemas.QuizSchema.model_validate(target_quiz)
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
    response_model=response.DataSchema[schemas.QuizSchema],
    status_code=200,
)
async def remove_quiz_questions(
    quiz_uid: QuizUID,
    data: schemas.QuizQuestionRemoveSchema,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    async with capture.capture(
        OperationalError,
        code=409,
        content="Cannot update quiz due to conflict",
    ):
        quiz = await crud.retrieve_quiz_by_uid(
            session,
            uid=quiz_uid,
            for_update=True,
        )

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    removed_questions = set()
    for question_uid in data.questions:
        question = await crud.retrieve_question_by_uid(session, question_uid)
        if not question:
            return response.notfound(f"Question with uid '{question_uid}' not found")
        if question not in quiz.questions:
            return response.notfound(
                f"Question with uid '{question_uid}' does not belong in quiz with uid '{quiz_uid}'"
            )
        removed_questions.add(question)

    target_quiz = quiz
    has_been_attempted = await crud.check_quiz_has_attempts(session, quiz_uid)
    if has_been_attempted:
        new_quiz = await crud.copy_quiz(quiz, is_latest=True)
        target_quiz = new_quiz
        new_quiz.questions -= removed_questions
        quiz.is_latest = False
        session.add(quiz)
    else:
        quiz.questions -= removed_questions

    target_quiz.difficulty = guess_quiz_difficulty(target_quiz.questions).value  # type: ignore
    session.add(target_quiz)
    await session.commit()
    await session.refresh(
        target_quiz,
        attribute_names=[
            "version",
            "questions_count",
            "created_by",
            "questions",
        ],
    )
    return response.success(
        "Quiz questions removed", data=schemas.QuizSchema.model_validate(target_quiz)
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
    response_model=response.DataSchema[None],
    status_code=200,
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
        quiz = await crud.retrieve_quiz_by_uid(
            session,
            uid=quiz_uid,
            for_update=True,
        )

    if not quiz or (quiz.created_by != user and not user.is_staff):
        return response.notfound("Quiz not found")

    # Delete older version of the quiz, leaving the latest only
    await crud.delete_quiz_by_uid(
        session,
        uid=quiz.uid,
        deleted_by_id=user.id,
        exclude_versions=[
            quiz.version,
        ],
    )
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
    response_model=response.DataSchema[schemas.QuizAttemptSchema],
    status_code=201,
)
async def create_quiz_attempt(
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
):
    quiz = await crud.retrieve_quiz_by_uid(session, uid=quiz_uid)
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
    response_model=PaginatedResponse[schemas.BaseQuizAttemptSchema],  # type: ignore
    status_code=200,
)
@cache(namespace="quiz_attempts", expire=10)
async def retrieve_quiz_attempts(
    request: fastapi.Request,
    quiz_uid: QuizUID,
    session: AsyncDBSession,
    user: ActiveUser[Account],
    ordering: QuizAttemptOrdering,
    quiz_version: QuizVersion = None,
    limit: typing.Annotated[Limit, Le(50)] = 50,
    offset: Offset = 0,
):
    filters = clean_params(
        ordering=ordering,
        limit=limit,
        offset=offset,
    )

    quiz = await crud.retrieve_quiz_by_uid(
        session,
        uid=quiz_uid,
        version=quiz_version,
    )
    if not quiz or (not quiz.is_public and not quiz.created_by == user):
        return response.notfound("Quiz not found")

    if quiz_version:
        filters["quiz_id"] = quiz.id
    
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
    response_model=response.DataSchema[schemas.QuizAttemptSchema],
    status_code=200,
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
    response_model=response.DataSchema[schemas.QuizAttemptSchema],
    status_code=200,
)
async def upsert_quiz_attempt_question_answer(
    quiz_uid: QuizUID,
    attempt_uid: QuizAttemptUID,
    question_uid: QuestionUID,
    data: schemas.QuizAttemptQuestionAnswerCreateSchema,
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
    if attempt.is_submitted:
        return response.unprocessable_entity("Quiz attempt already submitted")
    if attempt.is_expired:
        return response.unprocessable_entity("Quiz attempt duration elapsed")

    question = await crud.retrieve_question_in_quiz(
        session,
        question_uid=question_uid,
        quiz_id=attempt.quiz_id,
    )
    if not question:
        return response.notfound(
            "Question not found. Are you sure it belongs to this quiz?"
        )

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
    response_model=response.DataSchema[schemas.QuizAttemptSchema],
    status_code=200,
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
    if attempt.is_submitted:
        return response.conflict("Quiz attempt already submitted")
    if attempt.attempted_questions == 0:
        return response.unprocessable_entity("No questions attempted yet.")

    attempt.is_submitted = True
    attempt.submitted_at = timezone.now()
    session.add(attempt)
    await session.commit()
    return response.success(
        "Quiz attempt submitted",
        data=schemas.QuizAttemptSchema.model_validate(attempt),
    )


# TODO: Calculate quiz attempt score with background celery task

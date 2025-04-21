import typing
from collections import Counter

from apps.quizzes.models import QuizDifficulty, Question


def guess_quiz_difficulty(questions: typing.Sequence[Question]) -> QuizDifficulty:
    """Guess quiz difficulty based on questions."""
    if not questions:
        return QuizDifficulty.NOT_SET
    if len(questions) == 1:
        return QuizDifficulty(questions[0].difficulty)

    difficulties = [q.difficulty for q in questions]
    difficulty_counter = Counter(difficulties)
    return QuizDifficulty(difficulty_counter.most_common(1)[0][0])

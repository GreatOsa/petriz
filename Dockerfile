FROM python:3.12.8-alpine3.21

EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

WORKDIR /application

COPY ./poetry.lock ./pyproject.toml /application/

RUN pip install poetry

RUN poetry install --no-dev

COPY . /application

CMD ["poetry", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

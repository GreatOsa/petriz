FROM python:3.10.14-slim-bullseye

EXPOSE 8000

ENV PYTHONDONTWRITEBYTECODE=1

ENV PYTHONUNBUFFERED=1

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY . /app/

RUN uv sync --frozen

CMD ["uv", "run", "--python", "3.10", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
 
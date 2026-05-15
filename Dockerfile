FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install uv

FROM base AS deps
COPY pyproject.toml ./
RUN uv sync --frozen --no-dev 2>/dev/null || uv pip install --system \
    fastapi uvicorn[standard] gunicorn \
    asyncpg alembic \
    "pydantic[email]" pydantic-settings \
    "redis[asyncio]" httpx structlog bcrypt

FROM base AS runtime
COPY --from=deps /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=deps /usr/local/bin /usr/local/bin
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
EXPOSE 8900 8901
CMD ["python", "-m", "app.main"]

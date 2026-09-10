# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL="sqlite:////var/lib/shop-tracking/shop_tracking.db"

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        tesseract-ocr \
        tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app /var/lib/shop-tracking /app/backups \
    && chown -R appuser:appuser /app /var/lib/shop-tracking

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser migrations ./migrations
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser --chmod=755 docker/entrypoint.sh /usr/local/bin/shop-tracking
RUN sed -i 's/\r$//' /usr/local/bin/shop-tracking

USER appuser

EXPOSE 8000
ENTRYPOINT ["shop-tracking"]
CMD ["web", "--host", "0.0.0.0", "--port", "8000"]

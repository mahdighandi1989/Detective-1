# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# ---- System dependencies ----
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# ---- Builder stage: install python deps with Poetry ----
FROM base AS builder

# Install Poetry
ENV POETRY_HOME="/opt/poetry" \
    PATH="${POETRY_HOME}/bin:${PATH}" \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_NO_INTERACTION=1

# Install Poetry using its official installer script
RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy project files for dependency installation
COPY pyproject.toml poetry.lock ./

# Install project dependencies
# --no-dev to exclude development dependencies
# --no-root to not install the project itself (if it's a library)
# --compile to pre-compile Python files
RUN poetry install --no-root --no-dev --compile

# ---- Final runtime stage ----
FROM builder AS runtime

# Create non-root user
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /home/app app

# Remove Poetry and build-essential to slim down the final image
# Dependencies installed by Poetry remain in the system site-packages.
RUN rm -rf "${POETRY_HOME}" \
    && rm -rf /root/.cache/pypoetry \
    && apt-get remove -y --purge build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy application source
COPY . ${APP_HOME}

# Copy entrypoint
COPY ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chown -R app:app ${APP_HOME}

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]

# Use gunicorn to manage uvicorn workers for production deployment
# Assumes gunicorn and uvicorn.workers.UvicornWorker are installed via Poetry
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "--bind", "0.0.0.0:8000"]
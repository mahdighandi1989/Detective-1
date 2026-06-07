#!/usr/bin/env bash
set -euo pipefail

# Detective-1 backend entrypoint
# Waits for dependent services, runs migrations, then launches the app.

log() {
    echo "[entrypoint] $(date -u +'%Y-%m-%dT%H:%M:%SZ') $*"
}

# ---------------------------------------------------------------------------
# Configuration (overridable via env)
# ---------------------------------------------------------------------------
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

NEO4J_HOST="${NEO4J_HOST:-neo4j}"
NEO4J_PORT="${NEO4J_PORT:-7687}"

WAIT_FOR_NEO4J="${WAIT_FOR_NEO4J:-true}"
WAIT_FOR_REDIS="${WAIT_FOR_REDIS:-true}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-60}"

RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
RUN_SEED="${RUN_SEED:-false}"

APP_MODULE="${APP_MODULE:-app.main:app}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
APP_WORKERS="${APP_WORKERS:-1}"
RELOAD="${RELOAD:-false}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Wait for a TCP host:port to accept connections.
wait_for_tcp() {
    local name="$1"
    local host="$2"
    local port="$3"
    local timeout="$4"
    local elapsed=0

    log "Waiting for ${name} at ${host}:${port} (timeout ${timeout}s)..."
    while ! (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ "${elapsed}" -ge "${timeout}" ]; then
            log "ERROR: timed out waiting for ${name} at ${host}:${port}"
            return 1
        fi
    done
    exec 3>&- 2>/dev/null || true
    log "${name} is reachable at ${host}:${port}"
    return 0
}

run_migrations() {
    if [ "${RUN_MIGRATIONS}" = "true" ]; then
        log "Running database migrations (alembic upgrade head)..."
        if alembic upgrade head; then
            log "Migrations completed successfully."
        else
            log "ERROR: migrations failed."
            return 1
        fi
    else
        log "Skipping migrations (RUN_MIGRATIONS=${RUN_MIGRATIONS})."
    fi
}

run_seed() {
    if [ "${RUN_SEED}" = "true" ]; then
        log "Seeding initial data..."
        if python -m app.db.seed; then
            log "Seed completed successfully."
        else
            log "WARNING: seed step failed or no seed module present."
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    log "Starting Detective-1 backend entrypoint..."

    # Wait for required services
    wait_for_tcp "PostgreSQL" "${POSTGRES_HOST}" "${POSTGRES_PORT}" "${WAIT_TIMEOUT}"

    if [ "${WAIT_FOR_REDIS}" = "true" ]; then
        wait_for_tcp "Redis" "${REDIS_HOST}" "${REDIS_PORT}" "${WAIT_TIMEOUT}"
    fi

    if [ "${WAIT_FOR_NEO4J}" = "true" ]; then
        wait_for_tcp "Neo4j" "${NEO4J_HOST}" "${NEO4J_PORT}" "${WAIT_TIMEOUT}" || \
            log "WARNING: Neo4j not reachable; continuing anyway."
    fi

    # ------------------------------------------------------------------
    # Dispatch based on the first argument / container role.
    # ------------------------------------------------------------------
    case "${1:-api}" in
        api|web|server)
            run_migrations
            run_seed
            log "Launching API server (${APP_MODULE}) on ${APP_HOST}:${APP_PORT}..."
            if [ "${RELOAD}" = "true" ]; then
                exec uvicorn "${APP_MODULE}" \
                    --host "${APP_HOST}" \
                    --port "${APP_PORT}" \
                    --reload
            else
                exec uvicorn "${APP_MODULE}" \
                    --host "${APP_HOST}" \
                    --port "${APP_PORT}" \
                    --workers "${APP_WORKERS}"
            fi
            ;;

        worker|celery|celery-worker)
            log "Launching Celery worker..."
            exec celery -A app.workers.celery_app.celery_app worker \
                --loglevel="${CELERY_LOGLEVEL:-info}" \
                --concurrency="${CELERY_CONCURRENCY:-4}"
            ;;

        beat|celery-beat|scheduler)
            log "Launching Celery beat scheduler..."
            exec celery -A app.workers.celery_app.celery_app beat \
                --loglevel="${CELERY_LOGLEVEL:-info}"
            ;;

        flower)
            log "Launching Flower monitoring dashboard..."
            exec celery -A app.workers.celery_app.celery_app flower \
                --port="${FLOWER_PORT:-5555}"
            ;;

        migrate)
            run_migrations
            log "Migration-only run complete."
            ;;

        seed)
            run_seed
            log "Seed-only run complete."
            ;;

        shell|bash)
            log "Dropping into interactive shell..."
            exec /bin/bash
            ;;

        *)
            # Arbitrary command passthrough.
            log "Executing custom command: $*"
            exec "$@"
            ;;
    esac
}

main "$@"
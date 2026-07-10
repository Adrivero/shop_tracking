#!/bin/sh
set -eu

alembic upgrade head

if [ "${1:-}" = "web" ]; then
    shift
    exec python -m app.web "$@"
fi

exec python -m app.scan_one "$@"

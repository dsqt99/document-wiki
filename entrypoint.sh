#!/bin/sh
set -e

alembic upgrade head
python -m app.scripts.seed_knowledge_types || true
python -m app.scripts.seed_skills

exec "$@"

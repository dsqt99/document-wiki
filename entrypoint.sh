#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

echo "Seeding default knowledge types..."
python -m app.scripts.seed_knowledge_types || true
echo "Knowledge types seeding complete."

echo "Seeding built-in skills..."
python -m app.scripts.seed_skills
echo "Skills seeding complete."

exec "$@"

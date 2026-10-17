FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 libreoffice-nogui \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

# Dependencies first so Docker can cache this layer.
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf app build *.egg-info

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY skills/ ./skills/
COPY entrypoint.sh ./
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

RUN useradd --create-home appuser && mkdir -p /app/temp_uploads && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 5055

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5055"]

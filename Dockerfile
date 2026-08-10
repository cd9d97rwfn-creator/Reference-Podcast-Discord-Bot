FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/app/data/episodes.sqlite3

WORKDIR /app

COPY pyproject.toml README.md start.py ./
COPY src ./src
COPY data/episodes.sqlite3 ./data/episodes.sqlite3

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

HEALTHCHECK --interval=5m --timeout=30s --start-period=30s --retries=3 \
    CMD reference-healthcheck --skip-eval || exit 1

CMD ["python", "start.py"]

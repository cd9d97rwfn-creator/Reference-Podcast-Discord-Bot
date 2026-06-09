FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/episodes.sqlite3 \
    PORT=10000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY episodes.sqlite3 ./data/episodes.sqlite3

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

EXPOSE 10000

CMD ["reference-bot"]

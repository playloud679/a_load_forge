FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY webhooks/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src/ ./src/
COPY webhooks/ ./webhooks/

EXPOSE 8080
CMD exec uvicorn webhooks.main:app --host 0.0.0.0 --port ${PORT:-8080}

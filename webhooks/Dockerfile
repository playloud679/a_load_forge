FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY webhooks/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src/ ./src/
COPY webhooks/ ./webhooks/

EXPOSE 8080
CMD ["uvicorn", "webhooks.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY services/crawler_agent/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY services ./services
COPY tools/crawl_thiele_small.py ./tools/crawl_thiele_small.py

ENTRYPOINT ["python", "-m", "services.crawler_agent.agent"]
CMD ["run", "--manifest", "/config/crawler-agent-manifest.json", "--run-root", "/workspace/runs"]

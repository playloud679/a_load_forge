FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY VERSION README.md ui_app.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY src ./src
COPY tools ./tools
COPY data ./data
COPY assets ./assets
COPY examples ./examples

EXPOSE 8080
CMD exec streamlit run ui_app.py --server.address=0.0.0.0 --server.port=${PORT:-8080}

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_THEME_BASE=dark \
    STREAMLIT_THEME_PRIMARY_COLOR="#10B981" \
    STREAMLIT_THEME_BACKGROUND_COLOR="#000000" \
    STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR="#0A0F16" \
    STREAMLIT_THEME_TEXT_COLOR="#F3F4F6"

WORKDIR /app
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY VERSION README.md ui_app.py ./
COPY .streamlit/config.toml ./.streamlit/config.toml
COPY src ./src
COPY tools ./tools
COPY data/catalog_lsdb.json \
     data/catalog_proprietario.json \
     data/catalog_vituixcad.json \
     data/catalog_speakerboxlite.json \
     data/catalog_ztzaudio_lf_ferrite_presets.json \
     data/driver_prices.json \
     ./data/
COPY assets ./assets
COPY examples ./examples

EXPOSE 8080
CMD exec streamlit run ui_app.py --server.address=0.0.0.0 --server.port=${PORT:-8080}

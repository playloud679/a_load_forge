#!/usr/bin/env bash
# Launch Load Forge and open it in Safari (instead of the default browser).
set -e
cd "$(dirname "$0")"

PORT="${PORT:-8501}"
URL="http://localhost:${PORT}"

# Invoke Streamlit through this project's Python interpreter.  Console-script
# shebangs retain an absolute path when a virtualenv is moved or copied and can
# otherwise start Load Forge with another project's dependencies.
.venv/bin/python -m streamlit run ui_app.py \
    --server.headless true \
    --server.port "${PORT}" &
ST_PID=$!

# Tear down Streamlit when this script exits (e.g. Ctrl-C).
trap 'kill ${ST_PID} 2>/dev/null' EXIT INT TERM

# Wait until the server accepts connections, then open Safari.
until curl -s -o /dev/null "${URL}"; do
    sleep 0.5
done
open -a Safari "${URL}"

# Stay in the foreground until Streamlit exits / Ctrl-C.
wait ${ST_PID}

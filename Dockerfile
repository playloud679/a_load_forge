FROM ubuntu:22.04

LABEL maintainer="Acoustic Horn Generator Team"
LABEL description="Headless 3D modeling & slicing pipeline for Acoustic Horn Generator"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TZ=UTC

# ------------------------------------------------------------------
# System dependencies: Python 3.10, Blender, CuraEngine, pip
# ------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    blender \
    cura-engine \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# Application code
# ------------------------------------------------------------------
WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/           /app/src/
COPY blender_scripts/ /app/blender_scripts/
COPY configs/       /app/configs/

# ------------------------------------------------------------------
# Allow the host to read generated files via mounted volume
# ------------------------------------------------------------------
VOLUME /app/io

ENTRYPOINT ["python3", "-m", "src.main"]

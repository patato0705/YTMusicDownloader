# -------------------------
# 1. Build frontend (React + Vite)
# -------------------------
FROM node:24-slim AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN test -s package.json || (echo "Error: package.json empty or missing" && exit 1)
RUN npm ci --prefer-offline --no-audit --progress=false

COPY frontend/ .
RUN npm run build

# -------------------------
# 2. Runtime python image with supervisord
# -------------------------
FROM python:3.14-slim

# tzdata for TZ, ffmpeg for yt-dlp and cover conversion, curl for the compose
# healthcheck. No compiler: every Python dependency ships a prebuilt wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Copy backend requirements and install deps. --only-binary makes the build
# fail loudly if a dependency ever needs compiling, since there's no compiler.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --only-binary=:all: -r /app/backend/requirements.txt

# copy backend source
COPY backend/ /app/backend

# copy frontend build into backend static folder
COPY --from=frontend-builder /app/frontend/dist /app/backend/static

# copy supervisord config and startup entrypoint
COPY deploy/supervisord.conf /etc/supervisor/supervisord.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# create data dirs (will be mounted by compose typically)
RUN mkdir -p /data /config && chmod -R 0777 /data /config

# ensure backend package import works
ENV PYTHONPATH=/app

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
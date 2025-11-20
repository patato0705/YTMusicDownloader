# -------------------------
# 1. Build frontend (React + Vite)
# -------------------------
FROM node:20 AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN test -s package.json || (echo "Erreur: package.json vide ou manquant" && exit 1)
RUN npm ci --prefer-offline --no-audit --progress=false

COPY frontend/ .
RUN npm run build

# -------------------------
# 2. Runtime python image with supervisord
# -------------------------
FROM python:3.11-slim

# packages système nécessaires (ffmpeg, libmagic, libs pour Pillow, build tools, supervisor)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
        ffmpeg \
        git \
        libmagic1 \
        libjpeg-dev \
        zlib1g-dev \
        build-essential \
        supervisor \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Copy backend requirements and install deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# copy backend source
COPY backend/ /app/backend

# copy frontend build into backend static folder
COPY --from=frontend-builder /app/frontend/dist /app/backend/static

# copy supervisord config
COPY deploy/supervisord.conf /etc/supervisor/supervisord.conf

# create data dirs (will be mounted by compose typically)
RUN mkdir -p /data /data/music /data/covers /data/lyrics_raw /config && chmod -R 0777 /data /config

# ensure backend package import works
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
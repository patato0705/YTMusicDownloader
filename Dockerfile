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

# tzdata for TZ. Nothing else from apt: ffmpeg and uv come in as static
# binaries below, and the compose healthcheck uses python rather than curl.
# No compiler: every Python dependency ships a prebuilt wheel.
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# Static ffmpeg/ffprobe for yt-dlp's audio extraction (github.com/wader/static-ffmpeg).
# Debian's ffmpeg package drags in ~30 shared libraries (libxml2, libass,
# cjson, mesa, llvm...) that made up most of the image's CVE scan findings.
# Pinned by digest: to bump, pick a newer tag on Docker Hub and its digest.
COPY --from=mwader/static-ffmpeg:9.0.2-1@sha256:f5d100184884eb3e82b0eb14bb5ebf98da99826ac824989720297fb9ef21c822 /ffmpeg /ffprobe /usr/local/bin/

# uv installs the Python deps here and updates yt-dlp at startup
# (deploy/entrypoint.sh) in place of pip, which is uninstalled below: pip
# vendors its own copies of urllib3, msgpack and setuptools, and they lag
# behind on security fixes. Pinned by digest like ffmpeg above.
COPY --from=ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff /uv /usr/local/bin/

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy backend requirements and install deps. --only-binary makes the build
# fail loudly if a dependency ever needs compiling, since there's no compiler.
COPY backend/requirements.txt /app/backend/requirements.txt
RUN uv pip install --system --no-cache --only-binary :all: -r /app/backend/requirements.txt \
    && uv pip uninstall --system pip

# copy backend source
COPY backend/ /app/backend

# copy frontend build into backend static folder
COPY --from=frontend-builder /app/frontend/dist /app/backend/static

# copy supervisord config and startup entrypoint
COPY deploy/supervisord.conf /etc/supervisor/supervisord.conf
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Mount points (bind-mounted by compose); deploy/entrypoint.sh gives them to PUID:PGID
RUN mkdir -p /data /config

# ensure backend package import works
ENV PYTHONPATH=/app

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
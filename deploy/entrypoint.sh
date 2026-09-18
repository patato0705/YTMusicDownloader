#!/bin/sh
# Runs once per container start, before supervisord.
set -e

# -----------------------------------------------------------------------
# Prepare a non-root user matching the host, so files created in the
# bind-mounted /data and /config (music library, database, logs, covers)
# are owned by a real, deletable-by-you host user instead of root.
# Without this, everything the container writes ends up root-owned on
# the host -- you can't clean it up as yourself, and any other service
# (a media server, a backup job) that isn't also running as root can hit
# permission errors reading or writing the same files.
#
# supervisord itself still starts as root (needed for its own /dev/stdout
# log redirection -- see the `user=` directive in supervisord.conf,
# which is what actually drops each of web/worker/scheduler to PUID:PGID
# individually; supervisord dropping its own privileges wholesale breaks
# that redirection under Docker).
#
# Defaults to 1000:1000, the first regular user on most Linux installs.
# If that's not you, set PUID/PGID in docker-compose.yml -- check yours
# with `id -u` / `id -g` on the host.
# -----------------------------------------------------------------------
export PUID=${PUID:-1000}
export PGID=${PGID:-1000}

if ! getent group "$PGID" >/dev/null 2>&1; then
    groupadd -g "$PGID" appgroup
fi
if ! getent passwd "$PUID" >/dev/null 2>&1; then
    useradd -u "$PUID" -g "$PGID" -M -s /usr/sbin/nologin appuser
fi

# /config is small (db, logs, secrets, temp downloads) -- safe to chown
# recursively on every start. /data can be a large music library, so only
# the mount point itself is fixed; new files the app creates from here on
# already get the right ownership since web/worker/scheduler run as
# PUID:PGID. Files that already exist from before this change was
# deployed need a one-time manual chown (or a fresh start).
chown -R "$PUID:$PGID" /config 2>/dev/null || true
chown "$PUID:$PGID" /data 2>/dev/null || true

echo "[entrypoint] App will run as PUID=$PUID PGID=$PGID"

# Number of yt-dlp download worker processes supervisord starts (see the
# worker-download program in supervisord.conf). This is only the ceiling:
# how many of them actually take jobs is the download.max_concurrent
# setting in the admin panel (default 1), so 3 idle-capable processes cost
# nothing but a little RAM. Anything that isn't a positive integer falls
# back to 3 rather than letting supervisord refuse to start on a bad value.
# Keep the default in step with backend/config.py DOWNLOAD_WORKERS.
DOWNLOAD_WORKERS="${DOWNLOAD_WORKERS:-3}"
case "$DOWNLOAD_WORKERS" in
    ''|*[!0-9]*|0) DOWNLOAD_WORKERS=3 ;;
esac
export DOWNLOAD_WORKERS
echo "[entrypoint] Download workers: $DOWNLOAD_WORKERS"

# yt-dlp is deliberately left unpinned in requirements.txt (see the comment
# there) because YouTube breaks it often. Pulling the latest release here
# means a container restart alone can pick up an upstream fix -- no image
# rebuild needed. If PyPI is unreachable (offline homeserver, registry
# outage) this just logs and continues with whatever was baked into the
# image, rather than blocking startup. Runs as root, before supervisord,
# since it needs to write to site-packages.
# The extras pull the matching challenge-solver (yt-dlp-ejs) and a deno
# runtime -- see the note in backend/requirements.txt.
echo "[entrypoint] Updating yt-dlp..."
if pip install --no-cache-dir --disable-pip-version-check -U "yt-dlp[default,deno]"; then
    echo "[entrypoint] yt-dlp update OK: $(yt-dlp --version 2>/dev/null || echo unknown), deno $(deno --version 2>/dev/null | head -1 || echo missing)"
else
    echo "[entrypoint] yt-dlp update failed, continuing with the version baked into the image" >&2
fi

exec supervisord -n -c /etc/supervisor/supervisord.conf

#!/usr/bin/env bash
# Smoke test of the built image, started the way docker-compose.yml starts
# it: /config and /data bind-mounted, PUID/PGID set to the user running this.
#
# What the backend tests can't see: the entrypoint (PUID/PGID, /config
# permissions, the yt-dlp update), supervisord and its processes, the
# frontend build served by the API, and a second start on the same database.
#
# Usage (needs docker, curl and jq):
#   docker build -t ytmusicdownloader:test .
#   .github/scripts/docker-smoke-test.sh ytmusicdownloader:test
set -euo pipefail

IMAGE=${1:?usage: $0 IMAGE}
NAME=ytmd-smoke-$$
PORT=${SMOKE_PORT:-8484}
BASE=http://127.0.0.1:$PORT
PUID=$(id -u)
PGID=$(id -g)
WORK=$(mktemp -d)
mkdir "$WORK/config" "$WORK/data"

fail() {
    echo "::error::$*" >&2
    exit 1
}

step() {
    echo "--- $*"
}

finish() {
    local status=$?
    if [ "$status" -ne 0 ]; then
        echo "::group::Container log"
        docker logs "$NAME" 2>&1 || true
        echo "::endgroup::"
    fi
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    # What the container wrote belongs to PUID:PGID, the user running this
    rm -rf "$WORK" 2>/dev/null || true
    exit "$status"
}
trap finish EXIT

# The image's own HEALTHCHECK, polled every 2 s instead of 30 s. Failures
# during the start period don't count: the entrypoint updates yt-dlp first.
wait_healthy() {
    local health
    for _ in $(seq 1 90); do
        [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" = "true" ] || fail "the container stopped"
        health=$(docker inspect -f '{{.State.Health.Status}}' "$NAME")
        case "$health" in
            healthy) return 0 ;;
            unhealthy) fail "the container is unhealthy" ;;
        esac
        sleep 2
    done
    fail "not healthy after 180 s (status: $health)"
}

# fetch PATH STATUS: GET PATH into $WORK/body and $WORK/headers, failing on another status
fetch() {
    local code
    code=$(curl -sS -o "$WORK/body" -D "$WORK/headers" -w '%{http_code}' "$BASE$1")
    [ "$code" = "$2" ] || fail "GET $1 answered $code, expected $2"
}

# header NAME: that header of the last fetch, or nothing
header() {
    { grep -i -m 1 "^$1:" "$WORK/headers" || true; } | cut -d: -f2- | tr -d '\r' | sed 's/^ *//'
}

# The container's log so far, in $WORK/log. Read from the file rather than
# piped: under pipefail, `docker logs | grep -q` can fail on a match (grep
# exits first and docker logs gets SIGPIPE).
save_log() {
    docker logs "$NAME" >"$WORK/log" 2>&1
}

# first_line TEXT
first_line() {
    printf '%s' "${1%%$'\n'*}"
}

# The app's processes, each checked to run as PUID: their PIDs on one line,
# to compare later (a process that crashed and was restarted has a new one).
# The counts are supervisord.conf's, with the default DOWNLOAD_WORKERS (3).
processes() {
    docker exec -i "$NAME" python - "$PUID" <<'PY'
import os, sys

puid = int(sys.argv[1])
expected = {"uvicorn backend.main:app": 1, "backend.jobs.worker": 8, "backend.scheduler": 1}
found = {name: [] for name in expected}
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = b" ".join(f.read().split(b"\0")).decode()
        with open(f"/proc/{pid}/status") as f:
            uid = int(next(line for line in f if line.startswith("Uid:")).split()[1])
    except (OSError, StopIteration):
        continue
    for name in expected:
        if name in cmdline:
            if uid != puid:
                sys.exit(f"{cmdline.strip()} runs as uid {uid}, not PUID {puid}")
            found[name].append(int(pid))
counts = {name: len(pids) for name, pids in found.items()}
if counts != expected:
    sys.exit(f"processes: {counts}, expected {expected}")
print(" ".join(str(pid) for pids in found.values() for pid in sorted(pids)))
PY
}

step "Starting $IMAGE as $PUID:$PGID"
docker run -d --name "$NAME" \
    -p "127.0.0.1:$PORT:8484" \
    -v "$WORK/config:/config" -v "$WORK/data:/data" \
    -e PUID="$PUID" -e PGID="$PGID" \
    --health-interval=2s --health-start-period=120s --health-start-interval=2s \
    "$IMAGE" >/dev/null
wait_healthy

step "The API answers"
fetch /api/health 200
jq -e '.ok == true' "$WORK/body" >/dev/null || fail "/api/health: $(cat "$WORK/body")"
fetch /api/auth/config 200
[[ $(header content-type) == application/json* ]] || fail "/api/auth/config is $(header content-type)"
# An unknown API route is a JSON 404, not the frontend's page
fetch /api/no-such-route 404
[[ $(header content-type) == application/json* ]] || fail "/api/no-such-route is $(header content-type)"

step "The frontend is served, with its security headers"
fetch / 200
[[ $(header content-type) == text/html* ]] || fail "/ is $(header content-type)"
[[ $(header content-security-policy) == *"script-src 'self' 'sha256-"* ]] \
    || fail "/ has no policy allowing its inline script by hash: '$(header content-security-policy)'"
[ "$(header x-content-type-options)" = "nosniff" ] || fail "/ has no X-Content-Type-Options"
asset=$(first_line "$(grep -o '/static/assets/[^"]*\.js' "$WORK/body" || true)")
[ -n "$asset" ] || fail "index.html links no script under /static/assets/"
# Frontend routes are the same page (React Router handles them)
fetch /library 200
[[ $(header content-type) == text/html* ]] || fail "/library is $(header content-type)"
fetch "$asset" 200
[[ $(header content-type) == *javascript* ]] || fail "$asset is $(header content-type)"
[ "$(header cache-control)" = "public, max-age=31536000, immutable" ] \
    || fail "$asset is cached as '$(header cache-control)'"

step "The first administrator's password from the log signs in"
save_log
password=$(first_line "$(sed -n 's/.*with the password \([^ ]*\) (you.*/\1/p' "$WORK/log")")
[ -n "$password" ] || fail "no first administrator password in the log"
curl -sS -o "$WORK/body" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg password "$password" '{username: "admin", password: $password}')" \
    "$BASE/api/auth/login"
jq -e '.user.role == "administrator" and .user.must_change_password == true' "$WORK/body" >/dev/null \
    || fail "signing in as admin: $(cat "$WORK/body")"

step "Every process runs, as PUID, and stays up"
before=$(processes) || fail "the process check failed (above)"
sleep 10
after=$(processes) || fail "the process check failed (above)"
[ "$before" = "$after" ] || fail "processes restarted: $before, then $after"

# runs COMMAND...: it starts and exits 0 in the container
runs() {
    docker exec "$NAME" "$@" >/dev/null 2>&1 || fail "'$*' doesn't run in the image"
}

# Being on PATH isn't enough: a binary for another architecture is there
# too (the health check only looks for ffmpeg), and fails when run
step "The bundled programs run"
runs ffmpeg -version
runs ffprobe -version
runs deno --version
runs yt-dlp --version
runs uv --version

step "Files on the host belong to PUID:PGID, /config to it alone"
[ -f "$WORK/config/db.sqlite" ] || fail "no database in /config"
[ "$(stat -c '%u:%g' "$WORK/config/db.sqlite")" = "$PUID:$PGID" ] \
    || fail "db.sqlite belongs to $(stat -c '%u:%g' "$WORK/config/db.sqlite")"
[ "$(stat -c '%a' "$WORK/config")" = "700" ] || fail "/config is mode $(stat -c '%a' "$WORK/config")"
[ "$(stat -c '%u:%g' "$WORK/data")" = "$PUID:$PGID" ] || fail "/data belongs to $(stat -c '%u:%g' "$WORK/data")"

step "A restart picks up the same database"
docker restart "$NAME" >/dev/null
wait_healthy
fetch /api/health 200
save_log
created=$(grep -c "Created the first administrator" "$WORK/log" || true)
[ "$created" = "1" ] || fail "the first administrator was created $created times"

step "No tracebacks in the log"
save_log
if grep -q "Traceback" "$WORK/log"; then
    fail "the log has a traceback"
fi

echo "Smoke test passed"

#!/usr/bin/env bash
# Starts the API, the BFF and the web dev server in the background on every start of
# the dev container. Logs go to /tmp/dev-backend.log and /tmp/dev-web.log. A server
# that is already running is left alone. Stop them with: pkill -f uvicorn; pkill -f vite
set -uo pipefail

cd "$(dirname "$0")/.."

start() {
  local pattern=$1 log=$2
  shift 2
  if pgrep -f "$pattern" >/dev/null; then
    echo "already running: $pattern"
    return
  fi
  setsid nohup "$@" >"$log" 2>&1 < /dev/null &
}

start "uvicorn app.main" /tmp/dev-backend.log make backend
start "node_modules/.bin/vite" /tmp/dev-web.log make web

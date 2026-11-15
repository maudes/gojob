#!/bin/sh
# Production-style start: built web interface plus the backend, without auto-reload.
#   PORT      web interface port  (default 3210)
#   API_PORT  backend port        (default 8000)
cd "$(dirname "$0")/.." || exit 1
PORT="${PORT:-3210}"
API_PORT="${API_PORT:-8000}"
export GOJOB_API_URL="http://127.0.0.1:${API_PORT}"
trap 'kill 0' INT TERM EXIT
(cd backend && uv run uvicorn gojob.main:app --host 127.0.0.1 --port "$API_PORT") &
npx next start -p "$PORT" &
wait

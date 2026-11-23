#!/bin/sh
# Start the Python backend and the web interface together. Ctrl+C stops both.
#   PORT      web interface port  (default 3210)
#   API_PORT  backend port        (default 8000)
cd "$(dirname "$0")/.." || exit 1
PORT="${PORT:-3210}"
API_PORT="${API_PORT:-8000}"
export GOJOB_API_URL="http://127.0.0.1:${API_PORT}"
trap 'kill 0' INT TERM EXIT
(cd backend && uv run uvicorn gojob.api:app --host 127.0.0.1 --port "$API_PORT" --reload) &
npx next dev -p "$PORT" &
wait

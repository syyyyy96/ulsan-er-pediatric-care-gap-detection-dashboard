#!/bin/sh
cd "$(dirname "$0")"
url="http://127.0.0.1:8000/index.html"
health="http://127.0.0.1:8000/api/health"
if curl -fsS "$health" >/dev/null 2>&1; then
  open "$url"
  exit 0
fi
python3 server.py &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null' INT TERM
tries=0
while [ "$tries" -lt 20 ]; do
  if curl -fsS "$health" >/dev/null 2>&1; then
    open "$url"
    wait "$server_pid"
    exit $?
  fi
  sleep 0.5
  tries=$((tries + 1))
done
wait "$server_pid"

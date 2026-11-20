#!/usr/bin/env bash
# Smoke test for the job-queue image: runs a throwaway container with a tiny
# queue, checks submit / poll / backpressure, then checks SIGTERM drains cleanly.
#
# Usage: ops/scripts/smoke-test.sh [image]     (default image: job-queue:latest)
# Env:   SMOKE_PORT      host port to publish (default 18000)
#        SMOKE_PLATFORM  image platform, e.g. linux/amd64 (default: Docker's choice)
set -euo pipefail

IMAGE="${1:-job-queue:latest}"
PLATFORM_ARGS=()
[ -n "${SMOKE_PLATFORM:-}" ] && PLATFORM_ARGS=(--platform "$SMOKE_PLATFORM")
NAME="job-queue-smoke-$$"
PORT="${SMOKE_PORT:-18000}"
BASE="http://127.0.0.1:${PORT}"
BODY='{"task_type":"DATA_AGGREGATION","priority":1,"payload":{"dataset_id":"ds-9982","operations":["FILTER","SUMMARIZE"],"destination":"s3://output-bucket/report.csv"},"max_retries":3,"timeout_seconds":30}'

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; docker logs "$NAME" 2>&1 | tail -30 >&2 || true; exit 1; }
json() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

echo "== start container ($IMAGE, capacity=5, workers=2)"
docker run -d --name "$NAME" ${PLATFORM_ARGS[@]+"${PLATFORM_ARGS[@]}"} -p "${PORT}:8000" \
  -e QUEUE_CAPACITY=5 -e NUM_WORKERS=2 -e DRAIN_TIMEOUT_SECONDS=30 "$IMAGE" >/dev/null

for _ in $(seq 1 50); do
  curl -fsS "$BASE/v1/health" >/dev/null 2>&1 && break
  sleep 0.2
done
echo "health: $(curl -fsS "$BASE/v1/health" || fail "health never returned 200")"
echo "runs as: $(docker exec "$NAME" id -un) (uid $(docker exec "$NAME" id -u))"

echo "== submit one task and poll to COMPLETED"
resp=$(curl -sS -w '\n%{http_code}' -X POST "$BASE/v1/tasks" -H 'content-type: application/json' -d "$BODY")
code=$(tail -n1 <<<"$resp"); submitted=$(sed '$d' <<<"$resp")
[ "$code" = "202" ] || fail "submit returned $code: $submitted"
echo "202 $submitted"
task_id=$(json "['task_id']" <<<"$submitted")
status=""
for _ in $(seq 1 50); do
  task=$(curl -fsS "$BASE/v1/tasks/$task_id")
  status=$(json "['status']" <<<"$task")
  [ "$status" = "COMPLETED" ] && break
  sleep 0.1
done
[ "$status" = "COMPLETED" ] || fail "task stuck in $status"
echo "200 $task"

echo "== error contracts"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/v1/tasks/does-not-exist")
[ "$code" = "404" ] || fail "unknown task returned $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/v1/tasks" -H 'content-type: application/json' -d '{"payload":{}}')
[ "$code" = "400" ] || fail "invalid body returned $code"
code=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$BASE/v1/tasks/$task_id")
[ "$code" = "409" ] || fail "cancel of a completed task returned $code"
echo "404 unknown task, 400 invalid body, 409 cancel completed"

echo "== burst of 40 submissions against capacity 5"
accepted=0; rejected=0; other=0; ids=()
for _ in $(seq 1 40); do
  resp=$(curl -sS -w '\n%{http_code}' -X POST "$BASE/v1/tasks" -H 'content-type: application/json' -d "$BODY")
  code=$(tail -n1 <<<"$resp")
  case "$code" in
    202) accepted=$((accepted + 1)); ids+=("$(sed '$d' <<<"$resp" | json "['task_id']")") ;;
    429) rejected=$((rejected + 1)); last_429=$(sed '$d' <<<"$resp") ;;
    *) other=$((other + 1)) ;;
  esac
done
echo "accepted=$accepted rejected(429)=$rejected other=$other"
[ "$rejected" -gt 0 ] || fail "queue never pushed back"
[ "$other" -eq 0 ] || fail "unexpected status codes in burst"
echo "429 $last_429"
echo "health: $(curl -fsS "$BASE/v1/health")"

echo "== SIGTERM with work still queued (docker stop)"
start=$(date +%s)
docker stop -t 40 "$NAME" >/dev/null
elapsed=$(( $(date +%s) - start ))
exit_code=$(docker inspect -f '{{.State.ExitCode}}' "$NAME")
echo "stopped in ${elapsed}s, exit code $exit_code"
[ "$exit_code" = "0" ] || fail "container exited with $exit_code"
docker logs "$NAME" 2>&1 | tail -6

echo "PASS (accepted tasks before stop: ${#ids[@]})"

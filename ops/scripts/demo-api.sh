#!/usr/bin/env bash
# Live API demo — no manual task-id copying.
#
#   export BASE=http://152.42.157.49   # or http://localhost:8000
#   ./ops/scripts/demo-api.sh           # run everything
#   ./ops/scripts/demo-api.sh health    # one scenario
#
# Scenarios: all | health | happy | cancel | errors | backpressure
set -euo pipefail

BASE="${BASE:-http://152.42.157.49}"
BODY='{"task_type":"DATA_AGGREGATION","payload":{"dataset_id":"demo-1","operations":["FILTER","SUMMARIZE"],"destination":"s3://output-bucket/report.csv"}}'

pp() { python3 -m json.tool 2>/dev/null || cat; }

hdr() {
  echo
  echo "────────────────────────────────────────"
  echo " $1"
  echo "────────────────────────────────────────"
}

post_task() {
  curl -sS -X POST "$BASE/v1/tasks" \
    -H 'content-type: application/json' -d "${1:-$BODY}"
}

wait_done() {
  local id="$1" status="" i
  for i in $(seq 1 50); do
    status=$(curl -sS "$BASE/v1/tasks/$id" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    [[ "$status" == "COMPLETED" || "$status" == "FAILED" || "$status" == "CANCELLED" ]] && break
    sleep 0.1
  done
  echo "final status: $status"
  curl -sS "$BASE/v1/tasks/$id" | pp
}

scenario_health() {
  hdr "1) Health — LB + app are up"
  echo "GET $BASE/v1/health"
  curl -sS "$BASE/v1/health" | pp
}

scenario_happy() {
  hdr "2) Happy path — submit → poll → COMPLETED"
  echo "POST $BASE/v1/tasks"
  local body id
  body=$(post_task)
  pp <<<"$body"
  id=$(python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])" <<<"$body")
  echo
  echo "GET $BASE/v1/tasks/$id  (auto-poll)"
  wait_done "$id"
  echo "$id" > /tmp/job-queue-demo-last-id
}

scenario_cancel() {
  hdr "3) Cancel — mark a QUEUED task CANCELLED"
  echo "Burst submit so at least one stays QUEUED, then DELETE the last id"
  local id=""
  for i in $(seq 1 40); do
    id=$(curl -sS -X POST "$BASE/v1/tasks" \
      -H 'content-type: application/json' \
      -d "{\"task_type\":\"DATA_AGGREGATION\",\"payload\":{\"dataset_id\":\"burst-$i\"}}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
  done
  echo "DELETE $BASE/v1/tasks/$id"
  local resp code body
  resp=$(curl -sS -w '\n%{http_code}' -X DELETE "$BASE/v1/tasks/$id")
  code=$(tail -n1 <<<"$resp")
  body=$(sed '$d' <<<"$resp")
  echo "HTTP $code  (200 = cancelled while QUEUED; 409 = already running/done — both OK)"
  pp <<<"$body"
}

scenario_errors() {
  hdr "4) Error contracts — 404 / 400 / 409"
  echo "→ unknown task (expect 404)"
  curl -sS -o /dev/null -w "HTTP %{http_code}\n" "$BASE/v1/tasks/does-not-exist"

  echo "→ missing task_type (expect 400)"
  curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/v1/tasks" \
    -H 'content-type: application/json' -d '{"payload":{}}'

  echo "→ unknown task_type (expect 400)"
  curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X POST "$BASE/v1/tasks" \
    -H 'content-type: application/json' -d '{"task_type":"NOT_A_REAL_TYPE","payload":{}}'

  local id="${1:-}"
  if [[ -z "$id" && -f /tmp/job-queue-demo-last-id ]]; then
    id=$(cat /tmp/job-queue-demo-last-id)
  fi
  if [[ -z "$id" ]]; then
    id=$(curl -sS -X POST "$BASE/v1/tasks" -H 'content-type: application/json' -d "$BODY" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
    wait_done "$id" >/dev/null
  fi
  echo "→ cancel a finished task (expect 409)"
  curl -sS -o /dev/null -w "HTTP %{http_code}\n" -X DELETE "$BASE/v1/tasks/$id"
}

scenario_backpressure() {
  hdr "5) Backpressure — 429 when queue is full (local tiny capacity)"
  local name="job-queue-demo-bp" port=18000 local_base="http://127.0.0.1:${port}"
  local image="${DEMO_IMAGE:-registry.digitalocean.com/shridhar-job-queue/job-queue:latest}"

  if ! command -v docker >/dev/null; then
    echo "docker not available — skip backpressure demo"
    return 0
  fi

  docker rm -f "$name" >/dev/null 2>&1 || true
  echo "Starting throwaway container capacity=5 workers=1 …"
  docker run -d --name "$name" -p "${port}:8000" \
    -e QUEUE_CAPACITY=5 -e NUM_WORKERS=1 "$image" >/dev/null

  for _ in $(seq 1 50); do
    curl -fsS "$local_base/v1/health" >/dev/null 2>&1 && break
    sleep 0.2
  done

  local accepted=0 rejected=0 other=0 code
  for i in $(seq 1 40); do
    code=$(curl -sS -o /tmp/job-queue-bp-body -w '%{http_code}' -X POST "$local_base/v1/tasks" \
      -H 'content-type: application/json' \
      -d "{\"task_type\":\"DATA_AGGREGATION\",\"payload\":{\"dataset_id\":\"bp-$i\"}}")
    case "$code" in
      202) accepted=$((accepted + 1)) ;;
      429) rejected=$((rejected + 1)) ;;
      *) other=$((other + 1)) ;;
    esac
  done

  echo "submitted 40 → accepted(202)=$accepted  rejected(429)=$rejected  other=$other"
  if [[ "$rejected" -gt 0 ]]; then
    echo "sample 429 body:"
    pp </tmp/job-queue-bp-body
  fi
  echo "health under load:"
  curl -sS "$local_base/v1/health" | pp
  docker rm -f "$name" >/dev/null
  echo "throwaway container removed"
}

usage() {
  cat <<EOF
Usage: BASE=<url> $0 [all|health|happy|cancel|errors|backpressure]

  BASE defaults to http://152.42.157.49
  DEMO_IMAGE overrides the image used for backpressure (default: DOCR latest)

Examples:
  BASE=http://152.42.157.49 $0
  BASE=http://localhost:8000 $0 happy
EOF
}

main() {
  local cmd="${1:-all}"
  case "$cmd" in
    -h|--help|help) usage ;;
    health) scenario_health ;;
    happy) scenario_happy ;;
    cancel) scenario_cancel ;;
    errors) scenario_errors ;;
    backpressure) scenario_backpressure ;;
    all)
      scenario_health
      scenario_happy
      scenario_cancel
      scenario_errors
      scenario_backpressure
      echo
      echo "Done."
      ;;
    *)
      echo "Unknown scenario: $cmd" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"

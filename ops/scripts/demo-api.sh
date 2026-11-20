#!/usr/bin/env bash
# Live API demo — narrated, paced, no manual task-id copying.
#
#   export BASE=http://152.42.157.49   # or http://localhost:8000
#   ./ops/scripts/demo-api.sh           # all scenarios, with pauses
#   ./ops/scripts/demo-api.sh happy
#
# Env:
#   DEMO_PAUSE=enter   wait for Enter between beats (default for `all`)
#   DEMO_PAUSE=sleep   sleep DEMO_SLEEP seconds (default 2)
#   DEMO_PAUSE=off     no pauses
#   DEMO_SLEEP=2       used when DEMO_PAUSE=sleep
#   DEMO_IMAGE=...     image for backpressure throwaway container
set -euo pipefail

BASE="${BASE:-http://152.42.157.49}"
BODY='{"task_type":"DATA_AGGREGATION","payload":{"dataset_id":"demo-1","operations":["FILTER","SUMMARIZE"],"destination":"s3://output-bucket/report.csv"}}'
CMD="${1:-all}"

# Interactive by default when running the full show; single scenarios stay snappy
# unless the caller sets DEMO_PAUSE.
if [[ -z "${DEMO_PAUSE:-}" ]]; then
  if [[ "$CMD" == "all" ]]; then
    DEMO_PAUSE=enter
  else
    DEMO_PAUSE=sleep
  fi
fi
DEMO_SLEEP="${DEMO_SLEEP:-2}"

pp() { python3 -m json.tool 2>/dev/null || cat; }

say() { printf '%s\n' "$*"; }
note() { printf '  · %s\n' "$*"; }
blank() { echo; }

hdr() {
  blank
  echo "════════════════════════════════════════"
  echo " $1"
  echo "════════════════════════════════════════"
}

beat() {
  # Pause so the audience can read what just happened.
  case "$DEMO_PAUSE" in
    off|0|false) ;;
    sleep)
      sleep "$DEMO_SLEEP"
      ;;
    enter|*)
      blank
      printf '  [press Enter to continue] '
      read -r _
      ;;
  esac
}

post_task() {
  curl -sS -X POST "$BASE/v1/tasks" \
    -H 'content-type: application/json' -d "${1:-$BODY}"
}

http_code_body() {
  # Usage: http_code_body METHOD URL [curl args…]  → sets REPLY_CODE / REPLY_BODY
  local method="$1" url="$2"
  shift 2
  local resp
  resp=$(curl -sS -w '\n%{http_code}' -X "$method" "$url" "$@")
  REPLY_CODE=$(tail -n1 <<<"$resp")
  REPLY_BODY=$(sed '$d' <<<"$resp")
}

wait_done_narrated() {
  local id="$1" status="" prev="" i
  note "Polling GET /v1/tasks/$id until the worker finishes…"
  for i in $(seq 1 50); do
    status=$(curl -sS "$BASE/v1/tasks/$id" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    if [[ "$status" != "$prev" ]]; then
      note "status → $status"
      prev="$status"
    fi
    if [[ "$status" == "COMPLETED" || "$status" == "FAILED" || "$status" == "CANCELLED" ]]; then
      break
    fi
    sleep 0.15
  done
  blank
  say "Final task record:"
  curl -sS "$BASE/v1/tasks/$id" | pp
}

scenario_health() {
  hdr "1) Health — is the topology + app alive?"
  say "Calling the public entry point:"
  note "GET $BASE/v1/health"
  blank
  say "What to look for: status=HEALTHY, queue_capacity, total_workers."
  blank
  curl -sS "$BASE/v1/health" | pp
  beat
}

scenario_happy() {
  hdr "2) Happy path — submit is non-blocking, workers finish later"
  say "Step A — POST a job. The API should return 202 immediately with a task_id,"
  say "          even though the work has not finished yet."
  blank
  note "POST $BASE/v1/tasks"
  local id
  http_code_body POST "$BASE/v1/tasks" -H 'content-type: application/json' -d "$BODY"
  say "HTTP $REPLY_CODE  (expect 202 Accepted)"
  pp <<<"$REPLY_BODY"
  id=$(python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])" <<<"$REPLY_BODY")
  echo "$id" > /tmp/job-queue-demo-last-id
  beat

  say "Step B — Poll the same task. Watch status move QUEUED → RUNNING → COMPLETED."
  blank
  wait_done_narrated "$id"
  blank
  say "That proves: enqueue returned fast; a worker ran the handler; result is stored."
  beat
}

scenario_cancel() {
  hdr "3) Cancel — only QUEUED tasks can be cancelled"
  say "Workers finish ~200ms jobs quickly, so we burst-submit to leave some QUEUED."
  note "Submitting 40 tasks…"
  local id="" i
  for i in $(seq 1 40); do
    id=$(curl -sS -X POST "$BASE/v1/tasks" \
      -H 'content-type: application/json' \
      -d "{\"task_type\":\"DATA_AGGREGATION\",\"payload\":{\"dataset_id\":\"burst-$i\"}}" \
      | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
  done
  note "Last submitted id: $id"
  blank
  say "Now DELETE that id while it is hopefully still QUEUED:"
  note "DELETE $BASE/v1/tasks/$id"
  blank
  http_code_body DELETE "$BASE/v1/tasks/$id"
  say "HTTP $REPLY_CODE"
  pp <<<"$REPLY_BODY"
  blank
  case "$REPLY_CODE" in
    200) say "Got 200 CANCELLED — task was still waiting in the queue." ;;
    409) say "Got 409 — a worker already claimed it (RUNNING/COMPLETED). That is valid." ;;
    *) say "Unexpected code $REPLY_CODE" ;;
  esac
  beat
}

scenario_errors() {
  hdr "4) Error contracts — bad requests fail fast with the right code"
  blank

  say "→ Unknown task id (expect 404 Not Found)"
  http_code_body GET "$BASE/v1/tasks/does-not-exist"
  note "HTTP $REPLY_CODE"
  beat

  say "→ Missing task_type in body (expect 400 Bad Request)"
  http_code_body POST "$BASE/v1/tasks" -H 'content-type: application/json' -d '{"payload":{}}'
  note "HTTP $REPLY_CODE"
  [[ -n "$REPLY_BODY" ]] && pp <<<"$REPLY_BODY"
  beat

  say "→ Unknown task_type (expect 400 Bad Request)"
  http_code_body POST "$BASE/v1/tasks" -H 'content-type: application/json' \
    -d '{"task_type":"NOT_A_REAL_TYPE","payload":{}}'
  note "HTTP $REPLY_CODE"
  [[ -n "$REPLY_BODY" ]] && pp <<<"$REPLY_BODY"
  beat

  local id=""
  if [[ -f /tmp/job-queue-demo-last-id ]]; then
    id=$(cat /tmp/job-queue-demo-last-id)
  else
    id=$(post_task | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
    for _ in $(seq 1 50); do
      local st
      st=$(curl -sS "$BASE/v1/tasks/$id" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
      [[ "$st" == "COMPLETED" || "$st" == "FAILED" ]] && break
      sleep 0.1
    done
  fi
  say "→ Cancel a task that already finished (expect 409 Conflict)"
  note "DELETE $BASE/v1/tasks/$id"
  http_code_body DELETE "$BASE/v1/tasks/$id"
  note "HTTP $REPLY_CODE"
  [[ -n "$REPLY_BODY" ]] && pp <<<"$REPLY_BODY"
  blank
  say "Summary: 404 unknown · 400 invalid · 409 wrong state"
  beat
}

scenario_backpressure() {
  hdr "5) Backpressure — 202 while there is room, then 429 when full"
  say "Prod capacity is 10000, so we spin a throwaway local container with:"
  note "QUEUE_CAPACITY=3   NUM_WORKERS=1"
  say "That makes the queue fill up in front of your eyes."
  blank

  local name="job-queue-demo-bp"
  local port=18000
  local local_base="http://127.0.0.1:${port}"
  local image="${DEMO_IMAGE:-registry.digitalocean.com/shridhar-job-queue/job-queue:latest}"

  if ! command -v docker >/dev/null; then
    say "docker not available — skip backpressure demo"
    return 0
  fi

  docker rm -f "$name" >/dev/null 2>&1 || true
  note "Starting $image on :$port …"
  if ! docker run -d --name "$name" -p "${port}:8000" \
    -e QUEUE_CAPACITY=3 -e NUM_WORKERS=1 "$image" >/dev/null; then
    say "Could not start image. Build locally first: make build"
    say "Then: DEMO_IMAGE=registry.digitalocean.com/shridhar-job-queue/job-queue:latest $0 backpressure"
    return 1
  fi

  for _ in $(seq 1 50); do
    curl -fsS "$local_base/v1/health" >/dev/null 2>&1 && break
    sleep 0.2
  done

  blank
  say "Baseline health (empty queue):"
  curl -sS "$local_base/v1/health" | pp
  beat

  say "Submitting 25 tasks. Each line is one POST — watch codes flip from 202 → 429."
  note "202 = accepted (queue still had a free slot)"
  note "429 = rejected  (queue at capacity — fail-fast backpressure)"
  blank
  say "── Phase A: filling the queue (expect 202) ──"

  local accepted=0 rejected=0 other=0 code first_429="" i depth phase=A
  local -a sequence=()
  local sample_429=""

  for i in $(seq 1 25); do
    code=$(curl -sS -o /tmp/job-queue-bp-body -w '%{http_code}' -X POST "$local_base/v1/tasks" \
      -H 'content-type: application/json' \
      -d "{\"task_type\":\"DATA_AGGREGATION\",\"payload\":{\"dataset_id\":\"bp-$i\"}}")
    sequence+=("$code")

    depth=$(curl -sS "$local_base/v1/health" \
      | python3 -c "import sys,json; h=json.load(sys.stdin); print(f\"{h['queue_depth']}/{h['queue_capacity']}\")")

    case "$code" in
      202)
        accepted=$((accepted + 1))
        if [[ "$phase" == B ]]; then
          phase=C
          blank
          say "── Phase C: a slot freed (worker drained) — 202 can return briefly ──"
        fi
        printf '  #%02d  HTTP %s Accepted           queue=%s\n' "$i" "$code" "$depth"
        ;;
      429)
        rejected=$((rejected + 1))
        if [[ -z "$sample_429" ]]; then
          sample_429=$(cat /tmp/job-queue-bp-body)
        fi
        if [[ -z "$first_429" ]]; then
          first_429=$i
          phase=B
          blank
          say "── Phase B: queue FULL — further submits get 429 ──"
          printf '  #%02d  HTTP %s Too Many Requests  queue=%s  ← first rejection\n' \
            "$i" "$code" "$depth"
        else
          printf '  #%02d  HTTP %s Too Many Requests  queue=%s\n' "$i" "$code" "$depth"
        fi
        ;;
      *)
        other=$((other + 1))
        printf '  #%02d  HTTP %s (unexpected)      queue=%s\n' "$i" "$code" "$depth"
        ;;
    esac
    # Faster than the 200ms handler so the queue fills; still paced for reading.
    sleep 0.08
  done

  blank
  say "Full status sequence (left → right):"
  note "${sequence[*]}"
  blank

  if [[ -n "$first_429" ]]; then
    say "What happened:"
    note "1) Early requests returned HTTP 202 — work was enqueued."
    note "2) At request #$first_429 the bounded queue was full → HTTP 429."
    note "3) 429 is intentional backpressure (not a crash); client should retry later."
    note "4) If a worker frees a slot mid-burst, you may see 202 again (Phase C)."
  else
    say "No 429 seen — queue drained as fast as we filled it."
    note "Retry with DEMO_PAUSE=off, or: docker pull the image and run again."
  fi

  blank
  if [[ -n "$sample_429" ]]; then
    say "Sample 429 response body:"
    pp <<<"$sample_429"
  fi

  blank
  say "Health after the burst:"
  curl -sS "$local_base/v1/health" | pp
  blank
  say "Totals: accepted(202)=$accepted  rejected(429)=$rejected  other=$other"
  blank

  docker rm -f "$name" >/dev/null
  note "Throwaway container removed."
  beat
}

usage() {
  cat <<EOF
Usage: BASE=<url> $0 [all|health|happy|cancel|errors|backpressure]

  DEMO_PAUSE=enter|sleep|off   pacing (default: enter for all, sleep for one scenario)
  DEMO_SLEEP=2                 seconds when DEMO_PAUSE=sleep
  DEMO_IMAGE=<image>           image for the local backpressure container

Examples:
  BASE=http://152.42.157.49 $0
  DEMO_PAUSE=sleep DEMO_SLEEP=3 $0 happy
  $0 backpressure
EOF
}

main() {
  case "$CMD" in
    -h|--help|help) usage ;;
    health) scenario_health ;;
    happy) scenario_happy ;;
    cancel) scenario_cancel ;;
    errors) scenario_errors ;;
    backpressure) scenario_backpressure ;;
    all)
      say "Demo target: $BASE"
      say "Pacing: DEMO_PAUSE=$DEMO_PAUSE (set DEMO_PAUSE=off to rush)"
      scenario_health
      scenario_happy
      scenario_cancel
      scenario_errors
      scenario_backpressure
      blank
      say "Done — full showcase complete."
      ;;
    *)
      echo "Unknown scenario: $CMD" >&2
      usage >&2
      exit 1
      ;;
  esac
}

main

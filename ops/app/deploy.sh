#!/usr/bin/env bash
# Deploy job-queue from DOCR onto the Droplet via SSH + Docker Compose.
#
# Usage:
#   export DIGITALOCEAN_TOKEN=...   # registry pull (or rely on ~/.zshrc)
#   ops/app/deploy.sh               # TAG=latest
#   TAG=986ff28 ops/app/deploy.sh
#
# Env overrides:
#   DROPLET_HOST   default 168.144.210.142
#   DROPLET_USER   default root
#   LB_URL         default http://152.42.157.49
#   REMOTE_DIR     default /opt/job-queue
#   TAG            image tag (default latest)
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

DROPLET_HOST="${DROPLET_HOST:-168.144.210.142}"
DROPLET_USER="${DROPLET_USER:-root}"
LB_URL="${LB_URL:-http://152.42.157.49}"
REMOTE_DIR="${REMOTE_DIR:-/opt/job-queue}"
TAG="${TAG:-latest}"
REGISTRY_HOST="registry.digitalocean.com"
IMAGE="${REGISTRY_HOST}/shridhar-job-queue/job-queue:${TAG}"

SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${DROPLET_USER}@${DROPLET_HOST}")
SCP=(scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

if [ -z "${DIGITALOCEAN_TOKEN:-}" ]; then
  echo "DIGITALOCEAN_TOKEN is not set (needed for DOCR pull on the Droplet)." >&2
  exit 1
fi

echo "== target ${DROPLET_USER}@${DROPLET_HOST}  image ${IMAGE}"

echo "== sync compose to ${REMOTE_DIR}"
"${SSH[@]}" "mkdir -p '${REMOTE_DIR}'"
"${SCP[@]}" "${APP_DIR}/docker-compose.yml" "${DROPLET_USER}@${DROPLET_HOST}:${REMOTE_DIR}/docker-compose.yml"

if [ -f "${APP_DIR}/.env" ]; then
  "${SCP[@]}" "${APP_DIR}/.env" "${DROPLET_USER}@${DROPLET_HOST}:${REMOTE_DIR}/.env"
fi

echo "== docker login + pull + up"
TOKEN_B64="$(printf '%s' "$DIGITALOCEAN_TOKEN" | base64 | tr -d '\n')"
"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
TOKEN="\$(printf '%s' '${TOKEN_B64}' | base64 -d)"
printf '%s' "\$TOKEN" | docker login '${REGISTRY_HOST}' --username "\$TOKEN" --password-stdin >/dev/null
cd '${REMOTE_DIR}'
export TAG='${TAG}'
docker compose pull
docker compose up -d --remove-orphans
docker compose ps
REMOTE

echo "== wait for local health on droplet"
ok=0
for _ in $(seq 1 60); do
  if "${SSH[@]}" "curl -fsS http://127.0.0.1:8000/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" -ne 1 ]; then
  echo "FAIL: app did not become healthy on droplet" >&2
  "${SSH[@]}" "docker logs job-queue 2>&1 | tail -40" >&2 || true
  exit 1
fi

echo "== wait for LB health ${LB_URL}/v1/health"
ok=0
for _ in $(seq 1 90); do
  if curl -fsS "${LB_URL}/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 2
done
if [ "$ok" -ne 1 ]; then
  echo "FAIL: LB health check did not pass" >&2
  curl -sS -o /dev/stderr -w "\nHTTP %{http_code}\n" "${LB_URL}/v1/health" || true
  exit 1
fi

echo "== smoke: submit task via LB"
RESP="$(curl -fsS -X POST "${LB_URL}/v1/tasks" \
  -H 'content-type: application/json' \
  -d '{"task_type":"DATA_AGGREGATION","payload":{"dataset_id":"deploy-smoke"},"max_retries":1,"timeout_seconds":30}')"
echo "$RESP"
TASK_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["task_id"])' <<<"$RESP")"

ok=0
for _ in $(seq 1 40); do
  STATUS="$(curl -fsS "${LB_URL}/v1/tasks/${TASK_ID}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  if [ "$STATUS" = "COMPLETED" ] || [ "$STATUS" = "FAILED" ]; then
    echo "task ${TASK_ID} -> ${STATUS}"
    ok=1
    break
  fi
  sleep 0.5
done
[ "$ok" -eq 1 ] || { echo "FAIL: task did not finish" >&2; exit 1; }

echo "OK: deployed ${IMAGE}"
echo "    health: ${LB_URL}/v1/health"
echo "    ssh:    ssh ${DROPLET_USER}@${DROPLET_HOST}"

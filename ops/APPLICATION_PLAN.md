# Application Deployment Plan (Part 2)

Deploy the already-built image from DigitalOcean Container Registry onto the existing Droplet. Infrastructure (Part 1) stays owned by `ops/iac`; this plan only runs **one** container.

## Inputs (from prior agent work)

| Item | Value |
| :--- | :--- |
| Registry | `registry.digitalocean.com/shridhar-job-queue` |
| Image | `registry.digitalocean.com/shridhar-job-queue/job-queue` |
| Tags | `latest` + immutable git SHA (e.g. `986ff28`) |
| Platform | `linux/amd64` (matches Droplet) |
| Target host | Droplet `job-queue-1` (`168.144.210.142`) |
| Public entry | LB `http://152.42.157.49` → host `:8000` |
| Health | `GET /v1/health` |

See also: [app build & push session](aef509b6-9a7f-4a04-9964-4ae141e69656).

## Droplet readiness

| Prerequisite | Status |
| :--- | :--- |
| Docker Engine | **Ready** — `29.10.0`, cgroup v2, `overlayfs` |
| Docker Compose plugin | **Ready** — v5.8.0 |
| Port `8000` open (firewall) | **Ready** (Part 1) |
| LB → `:8000` | **Ready** (Part 1); health fails until container is up |
| DOCR login on Droplet | **Not yet** — required before first `docker pull` |

No host Python/app libs needed: the runtime is entirely inside the image.

## Recommended approach: Ansible (thin playbook)

**Why Ansible over Terraform for Part 2**

| Option | Fit |
| :--- | :--- |
| **Ansible** (recommended) | Idempotent pull/run/restart; good for “deploy this tag”; secrets via env/vault; does not churn Droplet resources |
| Terraform `null_resource` / `remote-exec` | Couples app deploys to infra state; `user_data` / taints risk Droplet replace |
| Plain SSH script | Fine for v0; weaker idempotency / inventory |
| Docker Compose on host | Good runtime unit; Ansible (or script) still needed to ship compose file + login + `up` |

**Pattern:** Ansible deploys a small Compose file and runs `docker compose up -d` on the Droplet.

```text
Laptop / CI
   │  ansible-playbook
   ▼
Droplet
   ├── docker login (DOCR)     # token or read-only registry key
   ├── docker compose pull
   └── docker compose up -d    # one service, port 8000, restart unless-stopped
         │
         ▼
Load Balancer ──► :8000 /v1/health
```

## Runtime contract (single container)

```yaml
# Conceptual compose — ops/app/docker-compose.yml
services:
  job-queue:
    image: registry.digitalocean.com/shridhar-job-queue/job-queue:${TAG:-latest}
    container_name: job-queue
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      PORT: "8000"
      QUEUE_CAPACITY: "10000"
      NUM_WORKERS: "16"
      DRAIN_TIMEOUT_SECONDS: "30"
    stop_grace_period: 40s   # > DRAIN_TIMEOUT_SECONDS
```

Constraints:

- **One replica only** (in-memory queue/store).
- Deploy = stop old → start new (brief downtime OK for v1).
- Prefer immutable SHA tag in prod; `latest` only for smoke.

## Proposed layout

```text
ops/
├── APPLICATION_PLAN.md          ← this file
├── app/
│   ├── docker-compose.yml       ← runtime definition on Droplet
│   ├── ansible.cfg
│   ├── inventory.ini            ← droplet IP from terraform output
│   └── playbooks/
│       └── deploy.yml           ← login, copy compose, pull, up, health check
└── iac/                         ← unchanged (infra only)
```

## Execution steps

1. **Registry auth on Droplet**  
   - Prefer DO **registry read-only** token / `doctl registry docker-config` written to `/root/.docker/config.json`  
   - Or one-time `docker login registry.digitalocean.com` with API token (avoid leaving write-capable token if possible)

2. **Ship compose** to `/opt/job-queue/docker-compose.yml`

3. **Deploy**  
   ```bash
   TAG=986ff28 ansible-playbook -i inventory.ini playbooks/deploy.yml -e image_tag=$TAG
   ```
   Playbook: login (if needed) → `docker compose pull` → `docker compose up -d` → wait for `/v1/health` on localhost:8000

4. **Verify via LB**  
   ```bash
   curl -fsS http://152.42.157.49/v1/health
   curl -fsS -X POST http://152.42.157.49/v1/tasks \
     -H 'content-type: application/json' \
     -d '{"task_type":"DATA_AGGREGATION","payload":{"dataset_id":"ds-1"}}'
   ```

5. **Rollback**  
   Re-run playbook with previous SHA tag.

## Secrets & config

| Secret / config | Handling |
| :--- | :--- |
| DOCR pull credential | Ansible var / env `DOCR_TOKEN`; not committed |
| App env | In compose or `.env` on host (`/opt/job-queue/.env`), gitignored example in repo |
| Inventory host IP | From `terraform output -raw droplet_ipv4` |

## Success criteria

- [ ] `docker ps` on Droplet shows `job-queue` healthy / running
- [ ] `curl http://127.0.0.1:8000/v1/health` → 200 on Droplet
- [ ] `curl http://<lb-ip>/v1/health` → 200 (LB backend green)
- [ ] Submit + poll task works through LB
- [ ] `docker stop` / redeploy drains within grace (no hard kill before 40s)

## Out of scope

- Changing VPC / Droplet / LB Terraform (unless adding a firewall tweak)
- Multi-instance / autoscaling
- CI wiring (can call the same playbook later)

## Decision

**Implemented:** SSH + Docker Compose via `ops/app/deploy.sh` (Ansible deferred — not required for v1).  
Terraform remains Part 1 only.

```bash
export DIGITALOCEAN_TOKEN=...
ops/app/deploy.sh                 # TAG=latest
TAG=<sha> ops/app/deploy.sh       # pin immutable tag
```

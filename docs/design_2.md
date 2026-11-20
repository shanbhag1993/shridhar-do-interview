# Design (as deployed today)

In-memory async job queue: **one process, one container, one Droplet**. FastAPI + bounded `asyncio.Queue` + worker pool. Public entry is the DigitalOcean load balancer.

---

## Topology

```mermaid
flowchart TB
    Clients(["HTTP Clients"])

    subgraph DO ["DigitalOcean · blr1"]
        LB["Load Balancer<br/>job-queue-lb<br/>152.42.157.49 :80"]
        FW["Cloud Firewall<br/>job-queue-fw<br/>allow TCP 22, 8000"]

        subgraph VPC ["VPC job-queue-vpc · 10.20.0.0/20"]
            Droplet["Droplet job-queue-1<br/>s-1vcpu-2gb · Ubuntu 24.04<br/>public 168.144.210.142<br/>private 10.20.0.2"]
            Container["Docker container<br/>job-queue :8000"]
            Droplet --- Container
        end

        DOCR[("DOCR<br/>shridhar-job-queue/job-queue")]
    end

    Clients -->|"HTTP :80"| LB
    LB -->|"forward → :8000<br/>health GET /v1/health"| FW
    FW --> Droplet
    DOCR -.->|"docker pull on deploy"| Container
    Clients -.->|"SSH :22"| FW
```

| Resource | Value |
| :--- | :--- |
| Region | `blr1` |
| VPC | `job-queue-vpc` (`10.20.0.0/20`) |
| Droplet | `job-queue-1` — `168.144.210.142` / `10.20.0.2` |
| Firewall | `job-queue-fw` — TCP 22, 8000 |
| Load balancer | `job-queue-lb` — `152.42.157.49:80` → `:8000` |
| Image | `registry.digitalocean.com/shridhar-job-queue/job-queue:release-v0.1.0` |
| Host path | `/opt/job-queue` (Compose) |
| App port | `8000` |

Path: **Client → LB :80 → Firewall → Droplet :8000 → container**. Single replica only (queue/store are in-process memory).

---

## Application design

```mermaid
flowchart TD
    Client(["HTTP Client"])

    subgraph API ["HTTP REST API"]
        Router["Router"]
        Validator["Validate + mint task_id"]
        Status["Status / Cancel handlers"]
    end

    subgraph State ["In-memory state"]
        Q[("asyncio.Queue<br/>bounded FIFO")]
        Store[("Task store<br/>dict + Lock + TTL")]
    end

    subgraph Workers ["Worker pool"]
        W1["Worker 1"]
        W2["Worker 2"]
        WN["Worker N"]
        Cleaner["TTL cleaner"]
    end

    Client -->|"POST /v1/tasks"| Router --> Validator
    Validator -->|"QUEUED"| Store
    Validator -->|"put_nowait"| Q
    Validator -->|"202 + task_id"| Client

    Client -->|"GET/DELETE /v1/tasks/{id}"| Status
    Status --> Store

    Q --> W1 & W2 & WN
    W1 & W2 & WN -->|"RUNNING → COMPLETED/FAILED"| Store
    Cleaner -->|"evict terminal after TTL"| Store
```

### Task lifecycle

```mermaid
stateDiagram-v2
    [*] --> QUEUED: POST /v1/tasks
    QUEUED --> RUNNING: worker claims
    RUNNING --> COMPLETED: success
    RUNNING --> QUEUED: retry + backoff
    RUNNING --> FAILED: timeout / retries exhausted
    QUEUED --> CANCELLED: DELETE while QUEUED
    COMPLETED --> [*]: TTL eviction
    FAILED --> [*]: TTL eviction
    CANCELLED --> [*]: TTL eviction
```

### Runtime defaults (Compose)

| Setting | Default |
| :--- | :--- |
| `QUEUE_CAPACITY` | `10000` |
| `NUM_WORKERS` | `16` |
| `RETENTION_TTL_SECONDS` | `3600` |
| `CLEANER_INTERVAL_SECONDS` | `60` |
| `DRAIN_TIMEOUT_SECONDS` | `30` |
| `stop_grace_period` | `40s` |

### API surface

| Method | Path | Notes |
| :--- | :--- | :--- |
| `POST` | `/v1/tasks` | `202` enqueue; `429` when queue full |
| `GET` | `/v1/tasks/{id}` | Status / result |
| `DELETE` | `/v1/tasks/{id}` | Cancel if still `QUEUED` (`409` otherwise) |
| `GET` | `/v1/health` | LB health + queue metrics |

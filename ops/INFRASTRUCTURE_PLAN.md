# Infrastructure Deployment Plan (IaC)

Part **1 of 2**. Application image/build/rollout is out of scope (Part 2).

## Goal

Define and apply DigitalOcean landing-zone resources with **Terraform** (or OpenTofu — same HCL), so VPC / Droplet / Firewall / Load Balancer are reproducible, reviewable, and destroyable.

```text
ops/iac  ──terraform apply──►  DigitalOcean
                                 ├── VPC
                                 ├── Droplet (Ubuntu, Docker via cloud-init)
                                 ├── Cloud Firewall
                                 └── Load Balancer → Droplet :8000
```

## Why Terraform (not one-off UI / MCP create)

| Approach | Use when |
| :--- | :--- |
| **Terraform / OpenTofu** | Source of truth for Part 1 (chosen) |
| MCP / UI / `doctl` | Discovery, debugging, break-glass only — then import or reconcile into TF |
| App CD (Part 2) | Image build/push + restart; may stay outside TF or use a thin deploy module later |

## Scope

### In scope (Part 1)

| Resource | Terraform resource (digitalocean provider) |
| :--- | :--- |
| VPC | `digitalocean_vpc` |
| SSH key (reference or manage) | `digitalocean_ssh_key` data / resource |
| Droplet | `digitalocean_droplet` + `user_data` (Docker install) |
| Cloud Firewall | `digitalocean_firewall` |
| Load Balancer | `digitalocean_loadbalancer` |
| Optional: Project | `digitalocean_project` + resources assignment |
| Optional: Monitoring alerts | later; enable droplet monitoring flag first |

### Out of scope (Part 2)

- Dockerfile / registry push
- App container run / compose
- Making LB health checks green
- App secrets / env for the queue service

## Defaults

| Setting | Value |
| :--- | :--- |
| Tool | Terraform `>= 1.5` + `digitalocean/digitalocean` provider |
| Region | Variable, default `nyc3` (override via `tfvars`) |
| Droplet | `s-1vcpu-2gb`, Ubuntu 24.04, name `job-queue-1` |
| App port | `8000` (LB target; app not deployed yet) |
| LB health | HTTP `/v1/health` on `8000` (expected **failing** until Part 2) |
| State | Local state initially; remote (DO Spaces / Terraform Cloud) optional hardening |

## Proposed repo layout

```text
ops/
├── DEPLOYMENT_PLAN.md
├── INFRASTRUCTURE_PLAN.md          ← this file
└── iac/
    ├── README.md                   ← how to init / plan / apply / destroy
    ├── versions.tf                 ← terraform + provider pins
    ├── providers.tf                ← digitalocean provider (token via env)
    ├── variables.tf
    ├── outputs.tf
    ├── main.tf                     ← thin root module wiring
    ├── terraform.tfvars.example
    ├── cloud-init/
    │   └── docker.yaml             ← install Docker on first boot
    └── modules/
        └── landing_zone/
            ├── main.tf             ← vpc, droplet, firewall, lb
            ├── variables.tf
            └── outputs.tf
```

Keep the root module thin; put real resources in `modules/landing_zone` so Part 2 can add an `app` module later without rewriting networking.

## Execution phases

### Phase A — Scaffold (no cloud changes)

1. Add `ops/iac` layout above
2. Pin provider; document `DIGITALOCEAN_TOKEN`
3. Encode defaults as variables + `terraform.tfvars.example`
4. Write cloud-init for Docker CE
5. `terraform init` + `terraform validate`

### Phase B — Plan

1. Copy `terraform.tfvars.example` → `terraform.tfvars` (gitignored)
2. Set `region`, `ssh_key_fingerprint` (or name), size
3. `terraform plan` — review create set: VPC, Droplet, Firewall, LB

### Phase C — Apply

1. `terraform apply`
2. Capture outputs → `ops/infrastructure/inventory.md` (or rely on `terraform output`)
3. Verify: Droplet `active`, SSH works, Docker present, LB IP exists
4. Accept LB unhealthy until Part 2

### Phase D — Handoff

1. Tag / commit IaC (never commit token or `terraform.tfvars` with secrets)
2. Document destroy: `terraform destroy`
3. Start Part 2 (app) against outputs: droplet IP, LB IP, region

## Auth & secrets

| Secret | How |
| :--- | :--- |
| DO API token | `export DIGITALOCEAN_TOKEN=...` (or `DIGITALOCEAN_ACCESS_TOKEN`) — not in git |
| SSH private key | Local agent / file for SSH verify — not in Terraform state as private material |
| SSH public key | Data source by fingerprint, or `digitalocean_ssh_key` from public key file |

## Success criteria

- [ ] `terraform plan` is clean and matches intended resources
- [ ] `terraform apply` creates VPC + Droplet + Firewall + LB
- [ ] Outputs expose droplet id/IP, LB IP, VPC id
- [ ] Re-apply is idempotent (no spurious replaces)
- [ ] `terraform destroy` tears down Part 1 cleanly
- [ ] No dependency on manual UI resource creation for the happy path

## Risks

| Risk | Mitigation |
| :--- | :--- |
| LB health failing | Expected pre-app; don’t block Part 1 on healthy backends |
| Droplet replace on user_data change | Keep cloud-init stable; app deploys via SSH/CI in Part 2 |
| State loss | Add remote backend before shared/team use |
| Drift from UI edits | Re-plan; forbid UI edits in runbook |

## Next step

Scaffold `ops/iac` (Phase A), then `plan` / `apply` once `DIGITALOCEAN_TOKEN` + SSH key are set.

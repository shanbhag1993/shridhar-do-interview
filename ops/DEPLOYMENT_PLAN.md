# Deployment Overview

Two tracks, both automation-first.

| Part | Doc | Tooling | Status |
| :--- | :--- | :--- | :--- |
| **1. Infrastructure** | [`INFRASTRUCTURE_PLAN.md`](./INFRASTRUCTURE_PLAN.md) | Terraform (`ops/iac/`) | **Done** (applied) |
| **2. Application** | [`APPLICATION_PLAN.md`](./APPLICATION_PLAN.md) | Ansible + Docker Compose on Droplet; image from DOCR | **Planned** |

**Rule:** long-lived DO network/compute resources go through Terraform. App rollouts go through Ansible (do not recreate the Droplet to ship a new tag).

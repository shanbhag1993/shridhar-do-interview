# Deployment Overview

Two tracks, both **automation-first** (Terraform / OpenTofu for infra; app deploy via Terraform remote-exec / cloud-init, or a separate CD pipeline later).

| Part | Doc | Tooling | Status |
| :--- | :--- | :--- | :--- |
| **1. Infrastructure** | [`INFRASTRUCTURE_PLAN.md`](./INFRASTRUCTURE_PLAN.md) | Terraform (`ops/iac/`) | **Active** |
| **2. Application** | TBD `APPLICATION_PLAN.md` | Image build + deploy automation (CI and/or Terraform) | Deferred |

**Rule:** no long-lived DigitalOcean resources created by hand or one-off API calls. All infra changes go through IaC apply (and destroy).

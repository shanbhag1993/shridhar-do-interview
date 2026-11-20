# Infrastructure inventory (blr1)

Applied via `ops/iac` on 2026-11-20.

| Resource | Name / value | ID |
| :--- | :--- | :--- |
| Region | `blr1` | — |
| VPC | `job-queue-vpc` (`10.20.0.0/20`) | `4c5cde40-ec71-4d00-8cfe-35c3fd66ed30` |
| SSH key | `job-queue-local` | `61035142` |
| Droplet | `job-queue-1` (`s-1vcpu-2gb`, Ubuntu 24.04) | `621576394` |
| Droplet public IPv4 | `168.144.210.142` | — |
| Droplet private IPv4 | `10.20.0.2` | — |
| Firewall | `job-queue-fw` (22, 8000 in) | `0c9a7688-1180-4cba-aebb-71ac327a303e` |
| Load Balancer | `job-queue-lb` | `f8490fd4-0fbb-46f0-8bff-88cd32867a2f` |
| LB public IP | `152.42.157.49` | — |
| App port | `8000` | — |

## Access

```bash
ssh root@168.144.210.142
curl -sS http://152.42.157.49/v1/health
```

## Application (Part 2)

| Item | Value |
| :--- | :--- |
| Image | `registry.digitalocean.com/shridhar-job-queue/job-queue:latest` |
| Host path | `/opt/job-queue` (Compose) |
| Deploy | `ops/app/deploy.sh` |
| Status | Running — LB health + smoke task OK (2026-11-20) |

Console: https://cloud.digitalocean.com/droplets/621576394

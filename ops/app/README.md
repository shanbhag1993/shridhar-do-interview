# Application deploy (Droplet)

Pulls `registry.digitalocean.com/shridhar-job-queue/job-queue` and runs **one** Compose service on the Droplet.

## Version → image tag

| You say / pass | Image tag deployed |
| :--- | :--- |
| **v0.1.0** / `VERSION=v0.1.0` | `…/job-queue:release-v0.1.0` |
| `VERSION=0.1.0` | `…/job-queue:release-v0.1.0` |
| `TAG=release-v0.1.0` | `…/job-queue:release-v0.1.0` |
| (default) | `…/job-queue:latest` |

Release branches are named `release-vX.Y.Z` and the Docker tag matches that branch name.

```bash
export DIGITALOCEAN_TOKEN=...   # or source ~/.zshrc
VERSION=v0.1.0 ops/app/deploy.sh
# same as:
TAG=release-v0.1.0 ops/app/deploy.sh
```

Defaults: Droplet `168.144.210.142`, LB `http://152.42.157.49`, remote dir `/opt/job-queue`.

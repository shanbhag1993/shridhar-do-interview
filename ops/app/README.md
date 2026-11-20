# Application deploy (Droplet)

Pulls `registry.digitalocean.com/shridhar-job-queue/job-queue` and runs **one** Compose service on the Droplet.

```bash
export DIGITALOCEAN_TOKEN=...   # or source ~/.zshrc
ops/app/deploy.sh               # TAG=latest
TAG=<git-sha> ops/app/deploy.sh
```

Defaults: Droplet `168.144.210.142`, LB `http://152.42.157.49`, remote dir `/opt/job-queue`.

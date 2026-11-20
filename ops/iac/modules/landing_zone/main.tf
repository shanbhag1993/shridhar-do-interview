resource "digitalocean_vpc" "this" {
  name        = "${var.project_name}-vpc"
  region      = var.region
  ip_range    = var.vpc_ip_range
  description = "VPC for ${var.project_name} landing zone"
}

resource "digitalocean_droplet" "app" {
  name         = var.droplet_name
  region       = var.region
  size         = var.droplet_size
  image        = var.droplet_image
  vpc_uuid     = digitalocean_vpc.this.id
  ssh_keys     = var.ssh_key_ids
  monitoring   = var.enable_monitoring
  user_data    = var.user_data
  tags         = var.tags
  graceful_shutdown = true
}

resource "digitalocean_firewall" "app" {
  name = "${var.project_name}-fw"

  droplet_ids = [digitalocean_droplet.app.id]
  tags        = var.tags

  # SSH — tighten source in a follow-up if needed
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # App port — required for DO Load Balancer health checks / forwarding
  inbound_rule {
    protocol         = "tcp"
    port_range       = tostring(var.app_port)
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_loadbalancer" "app" {
  name     = "${var.project_name}-lb"
  region   = var.region
  vpc_uuid = digitalocean_vpc.this.id

  forwarding_rule {
    entry_protocol  = "http"
    entry_port      = 80
    target_protocol = "http"
    target_port     = var.app_port
  }

  healthcheck {
    protocol                 = "http"
    port                     = var.app_port
    path                     = "/v1/health"
    check_interval_seconds   = 10
    response_timeout_seconds = 5
    healthy_threshold        = 3
    unhealthy_threshold      = 3
  }

  droplet_ids = [digitalocean_droplet.app.id]
}

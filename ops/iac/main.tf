locals {
  ssh_public_key = file(pathexpand(var.ssh_public_key_path))
  user_data      = file("${path.module}/cloud-init/docker.yaml")
}

resource "digitalocean_ssh_key" "local" {
  name       = var.ssh_key_name
  public_key = local.ssh_public_key
}

module "landing_zone" {
  source = "./modules/landing_zone"

  project_name      = var.project_name
  region            = var.region
  vpc_ip_range      = var.vpc_ip_range
  droplet_name      = var.droplet_name
  droplet_size      = var.droplet_size
  droplet_image     = var.droplet_image
  app_port          = var.app_port
  ssh_key_ids       = [digitalocean_ssh_key.local.id]
  user_data         = local.user_data
  enable_monitoring = var.enable_monitoring
  tags              = var.tags
}

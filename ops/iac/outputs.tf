output "region" {
  value = var.region
}

output "vpc_id" {
  value = module.landing_zone.vpc_id
}

output "vpc_ip_range" {
  value = module.landing_zone.vpc_ip_range
}

output "droplet_id" {
  value = module.landing_zone.droplet_id
}

output "droplet_name" {
  value = module.landing_zone.droplet_name
}

output "droplet_ipv4" {
  value       = module.landing_zone.droplet_ipv4
  description = "Public IPv4 — SSH: ssh root@<this>"
}

output "droplet_ipv4_private" {
  value = module.landing_zone.droplet_ipv4_private
}

output "firewall_id" {
  value = module.landing_zone.firewall_id
}

output "loadbalancer_id" {
  value = module.landing_zone.loadbalancer_id
}

output "loadbalancer_ip" {
  value       = module.landing_zone.loadbalancer_ip
  description = "Public LB IP — HTTP http://<this>/v1/health (app Part 2)"
}

output "app_port" {
  value = var.app_port
}

output "ssh_command" {
  value = "ssh root@${module.landing_zone.droplet_ipv4}"
}

output "lb_health_url" {
  value = "http://${module.landing_zone.loadbalancer_ip}/v1/health"
}

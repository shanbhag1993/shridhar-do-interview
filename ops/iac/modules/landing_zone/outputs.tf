output "vpc_id" {
  value = digitalocean_vpc.this.id
}

output "vpc_ip_range" {
  value = digitalocean_vpc.this.ip_range
}

output "droplet_id" {
  value = digitalocean_droplet.app.id
}

output "droplet_name" {
  value = digitalocean_droplet.app.name
}

output "droplet_ipv4" {
  value = digitalocean_droplet.app.ipv4_address
}

output "droplet_ipv4_private" {
  value = digitalocean_droplet.app.ipv4_address_private
}

output "firewall_id" {
  value = digitalocean_firewall.app.id
}

output "loadbalancer_id" {
  value = digitalocean_loadbalancer.app.id
}

output "loadbalancer_ip" {
  value = digitalocean_loadbalancer.app.ip
}

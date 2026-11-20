variable "project_name" {
  type        = string
  description = "Name prefix for DigitalOcean resources"
  default     = "job-queue"
}

variable "region" {
  type        = string
  description = "DigitalOcean region slug"
  default     = "blr1"
}

variable "vpc_ip_range" {
  type        = string
  description = "VPC subnet CIDR"
  default     = "10.20.0.0/20"
}

variable "droplet_name" {
  type        = string
  description = "Droplet hostname"
  default     = "job-queue-1"
}

variable "droplet_size" {
  type        = string
  description = "Droplet size slug"
  default     = "s-1vcpu-2gb"
}

variable "droplet_image" {
  type        = string
  description = "Droplet image slug"
  default     = "ubuntu-24-04-x64"
}

variable "app_port" {
  type        = number
  description = "Application listen port (LB target)"
  default     = 8000
}

variable "ssh_public_key_path" {
  type        = string
  description = "Path to SSH public key uploaded to DigitalOcean"
  default     = "~/.ssh/id_ed25519.pub"
}

variable "ssh_key_name" {
  type        = string
  description = "Name for the DigitalOcean SSH key resource"
  default     = "job-queue-local"
}

variable "enable_monitoring" {
  type        = bool
  description = "Enable DigitalOcean monitoring agent on the Droplet"
  default     = true
}

variable "tags" {
  type        = list(string)
  description = "Tags applied to resources that support them"
  default     = ["job-queue", "infra"]
}

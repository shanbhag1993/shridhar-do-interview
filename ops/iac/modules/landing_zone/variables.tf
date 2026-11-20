variable "project_name" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_ip_range" {
  type = string
}

variable "droplet_name" {
  type = string
}

variable "droplet_size" {
  type = string
}

variable "droplet_image" {
  type = string
}

variable "app_port" {
  type = number
}

variable "ssh_key_ids" {
  type        = list(string)
  description = "DigitalOcean SSH key IDs or fingerprints"
}

variable "user_data" {
  type        = string
  description = "Cloud-init user data for the Droplet"
}

variable "enable_monitoring" {
  type = bool
}

variable "tags" {
  type = list(string)
}

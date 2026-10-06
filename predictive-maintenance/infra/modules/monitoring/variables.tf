variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "container_app_id" {
  type = string
}

variable "max_replicas" {
  type = number
}

variable "alert_email" {
  type = string
}

variable "tags" {
  type = map(string)
}

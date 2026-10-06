variable "project_name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "suffix" {
  type = string
}

variable "container_app_identity_principal_id" {
  type = string
}

variable "cosmos_connection_string" {
  type      = string
  sensitive = true
}

variable "app_insights_connection_string" {
  type      = string
  sensitive = true
}

variable "tags" {
  type = map(string)
}

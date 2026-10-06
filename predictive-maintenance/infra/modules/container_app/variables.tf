variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "image_name" {
  type    = string
  default = "predictive-maintenance-api"
}

variable "image_tag" {
  type = string
}

variable "identity_id" {
  type = string
}

variable "app_insights_secret_id" {
  description = "Key Vault secret id (versionless) holding the Application Insights connection string."
  type        = string
}

variable "min_replicas" {
  type = number
}

variable "max_replicas" {
  type = number
}

variable "concurrent_requests_per_replica" {
  type = number
}

variable "cpu" {
  type = number
}

variable "memory" {
  type = string
}

variable "tags" {
  type = map(string)
}

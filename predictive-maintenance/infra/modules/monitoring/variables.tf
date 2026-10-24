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

variable "location" {
  type = string
}

variable "log_analytics_workspace_id" {
  description = "Workspace behind Application Insights; the error-rate alert queries it."
  type        = string
}

variable "api_role_name" {
  description = "OTEL_SERVICE_NAME of the API, i.e. its AppRoleName in Application Insights."
  type        = string
  default     = "pmaint-api"
}

variable "error_rate_threshold_percent" {
  type    = number
  default = 5
}

variable "error_rate_min_requests" {
  type    = number
  default = 20
}

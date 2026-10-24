variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "container_app_environment_id" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "image_name" {
  type    = string
  default = "predictive-maintenance-ui"
}

variable "image_tag" {
  type = string
}

variable "identity_id" {
  type = string
}

variable "identity_principal_id" {
  type = string
}

variable "identity_client_id" {
  type = string
}

variable "app_insights_secret_id" {
  type = string
}

variable "api_url" {
  description = "Public https URL of the API the dashboard calls."
  type        = string
}

variable "api_resource_id" {
  description = "Resource id of the API container app; the dashboard reads its replica metrics."
  type        = string
}

variable "resource_group_id" {
  type = string
}

variable "log_analytics_workspace_customer_id" {
  type = string
}

variable "model_storage_account" {
  type = string
}

variable "min_replicas" {
  type    = number
  default = 0
}

variable "max_replicas" {
  type    = number
  default = 2
}

variable "tags" {
  type = map(string)
}

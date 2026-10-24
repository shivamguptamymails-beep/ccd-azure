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

variable "log_analytics_workspace_customer_id" {
  type = string
}

variable "log_analytics_workspace_shared_key" {
  type      = string
  sensitive = true
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

variable "cosmos_secret_id" {
  description = "Key Vault secret id (versionless) holding the Cosmos DB connection string."
  type        = string
}

variable "identity_client_id" {
  description = "Client id of the user-assigned identity, used by the Azure SDKs inside the app."
  type        = string
}

variable "model_storage_account" {
  type = string
}

variable "model_version" {
  description = "Blob prefix (e.g. v1) of the model version to serve."
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

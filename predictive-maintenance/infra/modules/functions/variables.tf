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

variable "suffix" {
  type = string
}

variable "identity_id" {
  description = "User-assigned identity with Key Vault Secrets User, used to resolve Key Vault references."
  type        = string
}

variable "cosmos_secret_id" {
  description = "Key Vault secret id (versionless) holding the Cosmos DB connection string."
  type        = string
}

variable "app_insights_secret_id" {
  type = string
}

variable "log_analytics_workspace_id" {
  type = string
}

variable "action_group_id" {
  type = string
}

variable "tags" {
  type = map(string)
}

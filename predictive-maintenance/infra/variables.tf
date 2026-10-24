variable "project_name" {
  description = "Short project slug used in resource names (alphanumeric, no spaces)."
  type        = string
  default     = "pmaint"
}

variable "environment" {
  description = "Deployment environment: dev, staging or prod."
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of dev, staging, prod."
  }
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "centralindia"
}

variable "cosmos_location" {
  description = "Optional Cosmos DB region override when the main region lacks capacity."
  type        = string
  default     = null
}

variable "image_tag" {
  description = "Tag of the predictive-maintenance-api image in ACR to deploy. The CI/CD pipeline passes the Git SHA here."
  type        = string
  default     = "latest"
}

variable "model_version" {
  description = "Model version (blob prefix in the models container) the API serves. Upload a new version folder, then change this to roll it out without rebuilding the image."
  type        = string
  default     = "v1"
}

variable "min_replicas" {
  description = "Minimum Container App replicas. 0 allows scale-to-zero between demos/load tests."
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Maximum Container App replicas under load."
  type        = number
  default     = 10
}

variable "concurrent_requests_per_replica" {
  description = "KEDA HTTP scale rule: target concurrent requests per replica before scaling out."
  type        = number
  default     = 20
}

variable "container_cpu" {
  description = "vCPU per replica."
  type        = number
  default     = 0.5
}

variable "container_memory" {
  description = "Memory per replica (must pair with container_cpu per Azure's allowed combinations)."
  type        = string
  default     = "1Gi"
}

variable "enable_api_management" {
  description = "Provision Azure API Management (Consumption tier) in front of the Container App for API-key auth, rate limiting and quotas. Off by default to keep first-time deploys fast; turn on for the managed-gateway demo."
  type        = bool
  default     = false
}

variable "publisher_name" {
  description = "Required by Azure API Management even when unused by the demo."
  type        = string
  default     = "Predictive Maintenance Team"
}

variable "publisher_email" {
  description = "Required by Azure API Management; also used as the alert notification address if alert_email is left blank."
  type        = string
}

variable "alert_email" {
  description = "Email address for Azure Monitor scaling/health alerts. Defaults to publisher_email if unset."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "predictive-maintenance"
    course  = "CCD-mini-project"
  }
}

variable "enable_frontend" {
  description = "Deploy the Streamlit dashboard as a second Container App."
  type        = bool
  default     = true
}

variable "frontend_image_tag" {
  description = "Tag of the predictive-maintenance-ui image in ACR."
  type        = string
  default     = "bootstrap"
}

variable "enable_functions" {
  description = "Deploy the serverless Critical-prediction notifier (Azure Function on the Cosmos DB change feed)."
  type        = bool
  default     = true
}

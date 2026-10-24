resource "azurerm_container_app_environment" "this" {
  name                       = "cae-${var.project_name}-${var.environment}"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  log_analytics_workspace_id = var.log_analytics_workspace_id
  tags                       = var.tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# AzureRM 3.x does not expose the explicit environment mode used by newer APIs.
resource "azapi_update_resource" "environment_mode" {
  type        = "Microsoft.App/managedEnvironments@2026-07-01"
  resource_id = azurerm_container_app_environment.this.id
  body = {
    properties = {
      environmentMode = "WorkloadProfiles"
      appLogsConfiguration = {
        destination = "log-analytics"
        logAnalyticsConfiguration = {
          customerId = var.log_analytics_workspace_customer_id
          sharedKey  = var.log_analytics_workspace_shared_key
        }
      }
    }
  }
}

resource "azurerm_container_app" "api" {
  depends_on                   = [azapi_update_resource.environment_mode]
  name                         = "ca-${var.project_name}-${var.environment}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }

  registry {
    server   = var.acr_login_server
    identity = var.identity_id
  }

  secret {
    name                = "appinsights-connection-string"
    identity            = var.identity_id
    key_vault_secret_id = var.app_insights_secret_id
  }

  secret {
    name                = "cosmos-connection-string"
    identity            = var.identity_id
    key_vault_secret_id = var.cosmos_secret_id
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "api"
      image  = "${var.acr_login_server}/${var.image_name}:${var.image_tag}"
      cpu    = var.cpu
      memory = var.memory

      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }
      env {
        name  = "OTEL_SERVICE_NAME"
        value = "pmaint-api"
      }
      env {
        name  = "IMAGE_TAG"
        value = var.image_tag
      }
      env {
        name  = "MODEL_VERSION"
        value = var.model_version
      }
      env {
        name  = "MODEL_STORAGE_ACCOUNT"
        value = var.model_storage_account
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      env {
        name        = "COSMOS_CONNECTION_STRING"
        secret_name = "cosmos-connection-string"
      }

      # Model imports and loading need extra time on fractional CPU replicas.
      startup_probe {
        transport               = "HTTP"
        path                    = "/ready"
        port                    = 8000
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 10
      }

      # Generous timeouts: a replica saturated by scoring is slow, not dead.
      # The 1 s default restarted busy replicas mid-load-test (502s).
      liveness_probe {
        transport               = "HTTP"
        path                    = "/health"
        port                    = 8000
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 6
      }
      readiness_probe {
        transport               = "HTTP"
        path                    = "/ready"
        port                    = 8000
        interval_seconds        = 5
        timeout                 = 5
        failure_count_threshold = 3
      }
    }

    # KEDA's built-in HTTP scaler: scale out when concurrent requests per
    # replica crosses this target. This is the rule a load test (locustfile
    # in load_test/) exercises to visibly drive replica count up, then back
    # down to min_replicas once traffic subsides.
    http_scale_rule {
      name                = "http-concurrency"
      concurrent_requests = var.concurrent_requests_per_replica
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

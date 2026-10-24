# Streamlit dashboard. Reuses the API's managed identity (AcrPull, Key Vault
# secrets, blob read) and adds Monitoring Reader on the resource group so the
# dashboard can read replica metrics, App Insights logs, alerts and revisions.

resource "azurerm_role_assignment" "monitoring_reader" {
  scope                = var.resource_group_id
  role_definition_name = "Monitoring Reader"
  principal_id         = var.identity_principal_id
}

resource "azurerm_container_app" "ui" {
  name                         = "ca-${var.project_name}-ui-${var.environment}"
  container_app_environment_id = var.container_app_environment_id
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

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name   = "ui"
      image  = "${var.acr_login_server}/${var.image_name}:${var.image_tag}"
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "API_URL"
        value = var.api_url
      }
      env {
        name  = "API_RESOURCE_ID"
        value = var.api_resource_id
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = var.identity_client_id
      }
      env {
        name  = "AZURE_REGION"
        value = var.location
      }
      env {
        name  = "PORTAL_URL"
        value = "https://portal.azure.com/#@/resource${var.api_resource_id}/overview"
      }
      env {
        name  = "LOG_ANALYTICS_WORKSPACE_ID"
        value = var.log_analytics_workspace_customer_id
      }
      env {
        name  = "MODEL_STORAGE_ACCOUNT"
        value = var.model_storage_account
      }
      env {
        name  = "OTEL_SERVICE_NAME"
        value = "pmaint-dashboard"
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }

      liveness_probe {
        transport = "HTTP"
        path      = "/_stcore/health"
        port      = 8501
      }
      readiness_probe {
        transport = "HTTP"
        path      = "/_stcore/health"
        port      = 8501
      }
    }

    http_scale_rule {
      name                = "http-concurrency"
      concurrent_requests = 10
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8501
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }
}

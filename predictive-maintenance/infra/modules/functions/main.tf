# Serverless notifier (the synopsis's "AWS Lambda" module, as an Azure
# Function): the Cosmos DB change feed triggers it for each batch of new
# predictions, and it emits a CRITICAL_PREDICTION event for every Critical one.
# The alert below turns those events into email via the shared action group.
#
# Consumption (Y1) plan = pay per execution, scales to zero, no servers.

# The Functions runtime keeps its triggers' state and the deployed package
# here; kept apart from the model registry so app churn never touches models.
resource "azurerm_storage_account" "functions" {
  name                     = substr("stfn${replace(var.project_name, "-", "")}${var.environment}${var.suffix}", 0, 24)
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = var.tags
}

resource "azurerm_service_plan" "functions" {
  name                = "asp-${var.project_name}-fn-${var.environment}"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = var.tags
}

resource "azurerm_linux_function_app" "notifier" {
  name                       = "func-${var.project_name}-${var.environment}-${var.suffix}"
  resource_group_name        = var.resource_group_name
  location                   = var.location
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key
  https_only                 = true
  tags                       = var.tags

  # The shared identity already holds Key Vault Secrets User, so the
  # connection strings below are resolved from Key Vault, never stored here.
  identity {
    type         = "UserAssigned"
    identity_ids = [var.identity_id]
  }
  key_vault_reference_identity_id = var.identity_id

  site_config {
    # The provider manages this app setting through site_config; set as a
    # plain app setting it shows as drift on every plan.
    application_insights_connection_string = "@Microsoft.KeyVault(SecretUri=${var.app_insights_secret_id})"

    application_stack {
      python_version = "3.11"
    }
  }

  app_settings = {
    COSMOS_CONNECTION = "@Microsoft.KeyVault(SecretUri=${var.cosmos_secret_id})"
    # Build requirements.txt on Azure during zip deploy (az functionapp
    # deployment source config-zip --build-remote true).
    SCM_DO_BUILD_DURING_DEPLOYMENT = "true"
  }

  lifecycle {
    # Set by zip deploy, not by Terraform.
    ignore_changes = [app_settings["WEBSITE_RUN_FROM_PACKAGE"]]
  }
}

# Email when any Critical prediction was logged in the last 5 minutes. One
# email per window (not one per machine) keeps a load test from flooding the
# inbox; the alert resolves itself once Critical predictions stop.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "critical_prediction" {
  name                 = "alert-${var.project_name}-${var.environment}-critical-prediction"
  resource_group_name  = var.resource_group_name
  location             = var.location
  scopes               = [var.log_analytics_workspace_id]
  description          = "A machine was scored Critical: schedule immediate maintenance (raised by the notifier Function)."
  severity             = 2
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"

  criteria {
    query                   = <<-KQL
      AppTraces
      | where Message startswith "CRITICAL_PREDICTION"
      | parse Message with * "machine=" machine " probability=" probability:real " cause=" cause " endpoint=" *
      | project TimeGenerated, machine, probability, cause
    KQL
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 0

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  auto_mitigation_enabled = true

  action {
    action_groups = [var.action_group_id]
  }

  tags = var.tags
}

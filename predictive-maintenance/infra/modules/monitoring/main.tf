resource "azurerm_monitor_action_group" "this" {
  name                = "ag-${var.project_name}-${var.environment}"
  resource_group_name = var.resource_group_name
  short_name          = "pmaintops"

  email_receiver {
    name                    = "oncall"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }

  tags = var.tags
}

# Fires when the API has scaled out to its configured ceiling - a signal
# that either max_replicas needs raising or load has gone beyond what the
# system was sized for.
resource "azurerm_monitor_metric_alert" "scaled_to_max" {
  name                = "alert-${var.project_name}-${var.environment}-scaled-to-max"
  resource_group_name = var.resource_group_name
  scopes              = [var.container_app_id]
  description         = "Replica count has reached max_replicas - sustained peak load."
  severity            = 2
  frequency           = "PT1M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Replicas"
    aggregation      = "Maximum"
    operator         = "GreaterThanOrEqual"
    threshold        = var.max_replicas
  }

  action {
    action_group_id = azurerm_monitor_action_group.this.id
  }

  tags = var.tags
}

# Fires on repeated container restarts - crash-looping image or failing
# health probes - the signal the CI/CD rollback step also watches for.
resource "azurerm_monitor_metric_alert" "restart_spike" {
  name                = "alert-${var.project_name}-${var.environment}-restart-spike"
  resource_group_name = var.resource_group_name
  scopes              = [var.container_app_id]
  description         = "Replicas are restarting repeatedly."
  severity            = 1
  frequency           = "PT1M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "RestartCount"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 3
  }

  action {
    action_group_id = azurerm_monitor_action_group.this.id
  }

  tags = var.tags
}

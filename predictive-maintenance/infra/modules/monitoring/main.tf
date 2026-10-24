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

# Fires when the API's server-error rate crosses error_rate_threshold_percent.
# A rate needs request counts, which Container Apps metrics can't divide, so
# this is a log alert over the Application Insights requests table (the API
# is instrumented with OpenTelemetry; probe paths are excluded there). The
# minimum-volume guard stops one failed request on an idle API from paging.
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "error_rate" {
  name                 = "alert-${var.project_name}-${var.environment}-error-rate"
  resource_group_name  = var.resource_group_name
  location             = var.location
  scopes               = [var.log_analytics_workspace_id]
  description          = "API 5xx rate above ${var.error_rate_threshold_percent}% over 15 minutes (min ${var.error_rate_min_requests} requests)."
  severity             = 1
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"

  criteria {
    query                   = <<-KQL
      AppRequests
      | where AppRoleName == "${var.api_role_name}"
      | summarize total = count(), failed = countif(toint(ResultCode) >= 500)
      | where total >= ${var.error_rate_min_requests}
      | extend failure_pct = round(100.0 * failed / total, 2)
      | where failure_pct > ${var.error_rate_threshold_percent}
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
    action_groups = [azurerm_monitor_action_group.this.id]
  }

  tags = var.tags
}

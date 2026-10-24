# Azure API Management, Consumption tier: the managed "API Gateway &
# Routing" layer in front of the Container App - subscription-key auth,
# rate limiting and quotas, without running any gateway compute ourselves.
# Consumption tier is serverless (pay-per-call) but can take ~20-40 minutes
# to provision, so it is kept behind var.enable_api_management at the root
# module and is not on the critical path for the first deploy/demo.
resource "azurerm_api_management" "this" {
  name                = "apim-${var.project_name}-${var.environment}"
  location            = var.location
  resource_group_name = var.resource_group_name
  publisher_name      = var.publisher_name
  publisher_email     = var.publisher_email
  sku_name            = "Consumption_0"
  tags                = var.tags
}

resource "azurerm_api_management_api" "predictive_maintenance" {
  name                  = "predictive-maintenance-api"
  resource_group_name   = var.resource_group_name
  api_management_name   = azurerm_api_management.this.name
  revision              = "1"
  display_name          = "Predictive Maintenance Inference API"
  path                  = "pm"
  protocols             = ["https"]
  service_url           = "https://${var.backend_fqdn}"
  subscription_required = true
}

resource "azurerm_api_management_api_operation" "predict" {
  operation_id        = "predict"
  api_name            = azurerm_api_management_api.predictive_maintenance.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  display_name        = "Predict failure risk for one machine"
  method              = "POST"
  url_template        = "/predict"

  response {
    status_code = 200
  }
}

resource "azurerm_api_management_api_operation" "predict_batch" {
  operation_id        = "predict-batch"
  api_name            = azurerm_api_management_api.predictive_maintenance.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  display_name        = "Predict failure risk for a batch of machines"
  method              = "POST"
  url_template        = "/predict/batch"

  response {
    status_code = 200
  }
}

resource "azurerm_api_management_api_operation" "explain" {
  operation_id        = "explain"
  api_name            = azurerm_api_management_api.predictive_maintenance.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  display_name        = "Explain one machine's score (SHAP)"
  method              = "POST"
  url_template        = "/explain"

  response {
    status_code = 200
  }
}

resource "azurerm_api_management_api_operation" "ready" {
  operation_id        = "ready"
  api_name            = azurerm_api_management_api.predictive_maintenance.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  display_name        = "Readiness and serving model version"
  method              = "GET"
  url_template        = "/ready"

  response {
    status_code = 200
  }
}

resource "azurerm_api_management_api_operation" "metadata" {
  operation_id        = "model-metadata"
  api_name            = azurerm_api_management_api.predictive_maintenance.name
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  display_name        = "Model thresholds and comparison"
  method              = "GET"
  url_template        = "/model/metadata"

  response {
    status_code = 200
  }
}

resource "azurerm_api_management_product" "this" {
  product_id            = "predictive-maintenance"
  api_management_name   = azurerm_api_management.this.name
  resource_group_name   = var.resource_group_name
  display_name          = "Predictive Maintenance"
  subscription_required = true
  approval_required     = false
  published             = true
}

resource "azurerm_api_management_product_api" "this" {
  api_name            = azurerm_api_management_api.predictive_maintenance.name
  product_id          = azurerm_api_management_product.this.product_id
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
}

# Throttling: 60 calls/min per subscription key, 5,000 calls/week quota.
# This is what the synopsis means by "request throttling" at the gateway,
# as distinct from the Container App's own auto-scaling under load.
resource "azurerm_api_management_product_policy" "throttle" {
  product_id          = azurerm_api_management_product.this.product_id
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name

  xml_content = <<XML
<policies>
  <inbound>
    <base />
    <rate-limit calls="60" renewal-period="60" />
    <quota calls="5000" renewal-period="604800" />
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
XML
}

# A key for demos and the smoke test. Real consumers would each get their
# own subscription, so their calls are throttled and revocable separately.
resource "azurerm_api_management_subscription" "demo" {
  api_management_name = azurerm_api_management.this.name
  resource_group_name = var.resource_group_name
  product_id          = azurerm_api_management_product.this.id
  display_name        = "Demo key"
  state               = "active"
}

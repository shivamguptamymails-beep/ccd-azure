# Model artifact storage: joblib pipelines + risk_thresholds.json, versioned
# so a bad retrain/redeploy can be rolled back to the previous blob version.
# Mirrors the original synopsis's "S3 - model artifact storage and versioning".
resource "azurerm_storage_account" "models" {
  # Storage account names: lowercase alphanumeric only, <= 24 chars, globally unique.
  name                     = substr("st${replace(var.project_name, "-", "")}${var.environment}${var.suffix}", 0, 24)
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  blob_properties {
    versioning_enabled = true
  }

  tags = var.tags
}

resource "azurerm_storage_container" "models" {
  name                  = "models"
  storage_account_name  = azurerm_storage_account.models.name
  container_access_type = "private"
}

# Prediction/request log store: every scored machine (inputs, probability,
# risk level, likely cause) lands here for audit and future retraining data.
# Serverless Cosmos DB = pay-per-request, nothing to provision/size upfront -
# a good fit for a bursty inference workload that scales with demand.
resource "azurerm_cosmosdb_account" "this" {
  name                = "cosmos-${var.project_name}-${var.environment}-${var.suffix}"
  resource_group_name = var.resource_group_name
  location            = var.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }

  tags = var.tags
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = "predictions"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
}

resource "azurerm_cosmosdb_sql_container" "prediction_logs" {
  name                  = "prediction-logs"
  resource_group_name   = var.resource_group_name
  account_name          = azurerm_cosmosdb_account.this.name
  database_name         = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths   = ["/machine_id"]
  partition_key_version = 2
}

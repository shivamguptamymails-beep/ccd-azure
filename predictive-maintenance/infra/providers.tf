terraform {
  required_version = ">= 1.5"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.9"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.117"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state in Azure Storage, so `terraform apply` is safe to run from
  # CI/CD and from a teammate's laptop without clobbering state. Create the
  # storage account once by hand (or via infra/bootstrap/, not shown here),
  # then supply these via `terraform init -backend-config=...` so the
  # account name/key never need to live in this file.
  backend "azurerm" {
    # resource_group_name  = "rg-pmaint-tfstate"
    # storage_account_name = "<globally-unique-name>"
    # container_name       = "tfstate"
    # key                  = "predictive-maintenance.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = true
      recover_soft_deleted_key_vaults = true
    }
  }
}

provider "random" {}

provider "azapi" {}

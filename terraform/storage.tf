# Storage account name: alphanumeric only, max 24 chars
locals {
  storage_name = "stclinpl${var.environment}"  # e.g. stclinpl<env> (14 chars, Azure limit)
}

resource "azurerm_storage_account" "adls" {
  name                     = local.storage_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true  # ADLS Gen2 hierarchical namespace

  tags = local.tags
}

# Grant the Access Connector MSI blob access — used by Unity Catalog storage credentials
resource "azurerm_role_assignment" "databricks_storage" {
  scope                = azurerm_storage_account.adls.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.main.identity[0].principal_id

  depends_on = [azurerm_databricks_access_connector.main]
}

resource "azurerm_storage_container" "landing" {
  name                  = "landing"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "bronze_files" {
  name                  = "bronze-files"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "autoloader_schema" {
  name                  = "autoloader-schema"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "catalog_managed" {
  name                  = "catalog-managed"
  storage_account_name  = azurerm_storage_account.adls.name
  container_access_type = "private"
}

resource "azurerm_databricks_workspace" "main" {
  name                = "dbw-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.databricks_sku  # "premium" required for Unity Catalog

  tags = local.tags
}

# Access Connector: provides a managed identity for Unity Catalog storage credentials.
# This is the correct way to grant Databricks access to ADLS Gen2 (not workspace MSI).
resource "azurerm_databricks_access_connector" "main" {
  name                = "dbac-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

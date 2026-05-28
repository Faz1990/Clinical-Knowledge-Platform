resource "azurerm_databricks_workspace" "main" {
  name                = "dbw-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.databricks_sku  # "premium" required for Unity Catalog

  tags = local.tags
}

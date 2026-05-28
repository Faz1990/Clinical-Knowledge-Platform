resource "azurerm_data_factory" "main" {
  name                = "adf-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

# ADF MSI → ADLS: needed for Copy Activity to read/write storage
resource "azurerm_role_assignment" "adf_storage" {
  scope                = azurerm_storage_account.adls.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_data_factory.main.identity[0].principal_id
}

# Linked service: ADLS Gen2 via MSI (no stored credentials)
resource "azurerm_data_factory_linked_service_data_lake_storage_gen2" "adls" {
  name            = "ls_adls_clinical_platform"
  data_factory_id = azurerm_data_factory.main.id
  url             = "https://${azurerm_storage_account.adls.name}.dfs.core.windows.net"

  use_managed_identity = true

  depends_on = [azurerm_role_assignment.adf_storage]
}

# Linked service: Databricks (MSI auth)
# NOTE: After first `terraform apply`, go to Databricks workspace admin console
# and add the ADF MSI principal_id as a workspace user with "Can Restart" cluster permission.
resource "azurerm_data_factory_linked_service_azure_databricks" "databricks" {
  name            = "ls_databricks_clinical_platform"
  data_factory_id = azurerm_data_factory.main.id
  adb_domain      = "https://${azurerm_databricks_workspace.main.workspace_url}"

  msi_work_space_resource_id = azurerm_databricks_workspace.main.id

  existing_cluster_id = var.databricks_cluster_id

  depends_on = [azurerm_databricks_workspace.main]
}

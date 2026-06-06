output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "storage_account_name" {
  value = azurerm_storage_account.adls.name
}

output "storage_account_dfs_endpoint" {
  value = azurerm_storage_account.adls.primary_dfs_endpoint
}

output "adf_name" {
  value = azurerm_data_factory.main.name
}

output "adf_identity_principal_id" {
  value       = azurerm_data_factory.main.identity[0].principal_id
  description = "Add this principal to Databricks workspace as a user"
}

output "databricks_workspace_url" {
  value = "https://${azurerm_databricks_workspace.main.workspace_url}"
}

output "databricks_workspace_id" {
  value = azurerm_databricks_workspace.main.id
}

output "access_connector_id" {
  value       = azurerm_databricks_access_connector.main.id
  description = "Use this as the CONNECTOR value in CREATE STORAGE CREDENTIAL in Unity Catalog"
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

# Notebook widget defaults — paste these into your Auto Loader notebook
output "notebook_source_path" {
  value = "abfss://bronze-files@${azurerm_storage_account.adls.name}.dfs.core.windows.net/"
}

output "notebook_schema_location" {
  value = "abfss://autoloader-schema@${azurerm_storage_account.adls.name}.dfs.core.windows.net/bronze_guidelines/"
}

output "openai_endpoint" {
  value       = var.create_azure_openai ? azurerm_cognitive_account.openai[0].endpoint : null
  description = "Set as AZURE_OPENAI_ENDPOINT in .env"
}

output "openai_key" {
  value       = var.create_azure_openai ? azurerm_cognitive_account.openai[0].primary_access_key : null
  sensitive   = true
  description = "Set as AZURE_OPENAI_KEY in .env — retrieve with: terraform output -raw openai_key"
}

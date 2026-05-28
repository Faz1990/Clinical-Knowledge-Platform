resource "azurerm_key_vault" "main" {
  name                = "kv-clinpl-${var.environment}"  # max 24 chars
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Allow your own AAD identity full access (required to write secrets via CLI/TF)
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
    key_permissions    = ["Get", "List", "Create", "Delete"]
  }

  # ADF MSI: read secrets only
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = azurerm_data_factory.main.identity[0].principal_id

    secret_permissions = ["Get", "List"]
  }

  tags = local.tags
}

# ADF linked service to Key Vault (for secret-referencing in pipelines)
resource "azurerm_data_factory_linked_service_key_vault" "main" {
  name            = "ls_keyvault_clinical_platform"
  data_factory_id = azurerm_data_factory.main.id
  key_vault_id    = azurerm_key_vault.main.id
}

# Azure Database for PostgreSQL Flexible Server — cloud production equivalent of Docker dev setup.
# Not deployed by default (create_azure_postgres = false).
# Interview framing: "containerised pgvector with Docker for dev;
# Azure Database for PostgreSQL Terraform included for cloud deploy."

resource "azurerm_postgresql_flexible_server" "pgvector" {
  count = var.create_azure_postgres ? 1 : 0

  name                   = "psql-${var.project_name}-${var.environment}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "16"
  administrator_login    = "clinical"
  administrator_password = var.postgres_admin_password
  sku_name               = "B_Standard_B1ms"  # cheapest burstable tier
  storage_mb             = 32768
  backup_retention_days  = 7
  tags                   = local.tags
}

resource "azurerm_postgresql_flexible_server_configuration" "pgvector_ext" {
  count     = var.create_azure_postgres ? 1 : 0
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.pgvector[0].id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_database" "clinical_platform" {
  count     = var.create_azure_postgres ? 1 : 0
  name      = "clinical_platform"
  server_id = azurerm_postgresql_flexible_server.pgvector[0].id
  collation = "en_US.utf8"
  charset   = "UTF8"
}

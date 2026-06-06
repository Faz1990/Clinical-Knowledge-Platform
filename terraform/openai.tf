# Azure OpenAI — embedding + chat models for the RAG serving layer.
# Not deployed by default (create_azure_openai = false).
# Interview framing: "Azure OpenAI provisioned via Terraform; local dev uses the same
# endpoint — no code change between environments, just env vars."
#
# Azure OpenAI availability varies by region. eastus has the broadest model coverage;
# override openai_location if your subscription quota is allocated elsewhere.

resource "azurerm_cognitive_account" "openai" {
  count = var.create_azure_openai ? 1 : 0

  name                = "oai-${var.project_name}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.openai_location
  kind                = "OpenAI"
  sku_name            = "S0"
  tags                = local.tags
}

resource "azurerm_cognitive_deployment" "embedding" {
  count                = var.create_azure_openai ? 1 : 0
  name                 = "text-embedding-3-small"
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = "text-embedding-3-small"
    version = "1"
  }

  scale {
    type     = "Standard"
    capacity = 120
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  count                = var.create_azure_openai ? 1 : 0
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-11-20"
  }

  scale {
    type     = "Standard"
    capacity = 30
  }
}

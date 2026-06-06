variable "subscription_id" {
  type        = string
  description = "Azure subscription ID"
}

variable "project_name" {
  type    = string
  default = "clinical-platform"
}

variable "environment" {
  type    = string
  default = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod."
  }
}

variable "location" {
  type    = string
  default = "uksouth"
}

variable "databricks_sku" {
  type        = string
  default     = "premium"
  description = "Premium required for Unity Catalog"
}

variable "allowed_ip_ranges" {
  type        = list(string)
  default     = []
  description = "Your public IP(s) for Key Vault firewall. Add with: az network public-ip show..."
}

variable "databricks_cluster_id" {
  type        = string
  default     = null
  description = "Existing Databricks cluster ID for ADF linked service. Leave null on first apply (workspace doesn't exist yet). Create a cluster in the Databricks UI after first apply, then set this and re-apply."
}

variable "create_azure_postgres" {
  type        = bool
  default     = false
  description = "Deploy Azure Database for PostgreSQL Flexible Server. Set true for cloud production deploy; dev uses Docker pgvector instead."
}

variable "postgres_admin_password" {
  type        = string
  default     = null
  sensitive   = true
  description = "Admin password for Azure PostgreSQL. Required when create_azure_postgres = true."
}

variable "create_azure_openai" {
  type        = bool
  default     = false
  description = "Deploy Azure OpenAI resource with embedding + chat deployments. Set true to provision; dev uses the same endpoint via env vars."
}

variable "openai_location" {
  type        = string
  default     = "eastus"
  description = "Region for Azure OpenAI. eastus has the broadest model coverage; override if quota is allocated elsewhere."
}

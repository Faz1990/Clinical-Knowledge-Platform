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

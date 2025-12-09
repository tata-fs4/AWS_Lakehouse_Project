variable "region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "account_id" {
  type        = string
  description = "AWS account id used for bucket naming"
}

variable "domains" {
  description = "Domain prefixes for Glue crawlers"
  type = map(object({
    prefix = string
  }))
  default = {
    erp     = { prefix = "erp_orders" }
    crm     = { prefix = "crm_leads" }
    web     = { prefix = "web_events" }
    product = { prefix = "products" }
  }
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet ids for MWAA"
}

variable "security_group_id" {
  type        = string
  description = "Security group used by MWAA"
}

variable "openlineage_endpoint" {
  type        = string
  description = "HTTP endpoint for OpenLineage emitter"
}

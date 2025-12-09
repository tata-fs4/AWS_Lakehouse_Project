output "raw_bucket" {
  value       = aws_s3_bucket.raw.bucket
  description = "Raw landing bucket"
}

output "curated_bucket" {
  value       = aws_s3_bucket.curated.bucket
  description = "Curated/processed bucket"
}

output "glue_database" {
  value       = aws_glue_catalog_database.lakehouse.name
  description = "Glue database for raw tables"
}

output "mwaa_webserver_url" {
  value       = aws_mwaa_environment.this.webserver_url
  description = "MWAA console URL"
}

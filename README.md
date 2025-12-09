# AWS Lakehouse with Airflow + dbt

This repository contains an opinionated example of a lakehouse architecture on AWS, featuring ingestion with Airflow/MWAA, cataloging with AWS Glue, transformations with dbt, and publication in Athena using Parquet partitioned by `dt` and `store_id` with Z-Order layout optimization.

## Components

- **S3:** Raw and curated buckets for landing and processed layers.  
- **Glue:** Databases and crawlers per domain (ERP, CRM, web, product catalog).  
- **Airflow (MWAA):** DAGs `ingest_{domain}`, `validate_{domain}`, `transform_{domain}`, and `publish_{domain}` with retries, SLA handlers, and Slack notifications.  
- **Great Expectations:** Minimal suites stored under `great_expectations/expectations`, executed during the `validate_*` stage.  
- **dbt:** Staging models and the fact table `fct_daily_store_metrics`, with manifest/docs generated via `dbt docs generate` and stored in the curated bucket.  
- **Athena:** Views and queries on the transformed layer; partitioning by `dt/store_id` with Z-Order reflected in file layout.  
- **OpenLineage:** Backend enabled in MWAA for lineage tracking across DAGs.  
- **Terraform:** Infrastructure provisioning for S3, Glue, MWAA, and IAM.

## Structure

airflow/dags/ # DAGs and callbacks
samples/ # Simulated ERP/CRM/web/products datasets
dbt/ # dbt project (models, seeds, manifest/docs)
great_expectations/ # Basic expectation suites
terraform/ # AWS IaC
Makefile # Deployment shortcuts
README.md

## Simulated Data

CSV/JSON files in `samples/` represent the expected domains: `erp_orders.csv`, `crm_leads.csv`, `web_events.json`, and `products.csv`.  
These files are also copied into `dbt/seeds/` for local dbt runs.

## Pipeline (One DAG per Domain)

- **ingest_{domain}:** Reads from `s3://lakehouse-raw/<domain>/` and triggers the appropriate Glue crawler.  
- **validate_{domain}:** Executes the corresponding Great Expectations checkpoint.  
- **transform_{domain}:** Runs `dbt build --select <domain>`, using incremental models, partitioning by `dt/store_id`, `incremental_strategy: merge`, and applying Z-Order via optimized Parquet layout.  
- **publish_{domain}:** Creates/updates Athena views in the curated layer and uploads dbt manifest/docs.  

DAGs include retries, `on_failure_callback` (Slack), `sla_miss_callback`, and `max_active_runs=1`.  
OpenLineage is configured via `airflow_configuration_options` in MWAA.

## Deployment

### Requirements
- Terraform >= 1.5  
- AWS CLI configured  
- `dbt-athena-community` installed  
- AWS account with appropriate permissions  

### Steps

make terraform-init # initialize backend
make terraform-plan # preview changes (provide TF_VAR_account_id, etc.)
make terraform-apply # creates buckets, Glue, MWAA

After provisioning, extract bucket names:

export RAW_BUCKET=$(terraform -chdir=terraform output -raw raw_bucket)
export CURATED_BUCKET=$(terraform -chdir=terraform output -raw curated_bucket)

Then publish artifacts:

make package-dbt # seeds + staging + marts + docs
make upload-dags # sync DAGs to MWAA source bucket
make upload-dbt-docs # publish manifest/docs to curated bucket

## Local Execution (QA)

Python dependencies: `pandas` (already included in MWAA base image).  
Run an end-to-end local workflow using simulated data:

cd aws_lakehouse_project
python local_runner.py --output-dir ./local_output

## or: make local-run
## This command:

- Validates datasets using GE suites in `great_expectations/expectations`  
- Creates staging tables mimicking dbt behavior  
- Materializes `fct_daily_store_metrics` under `local_output/curated/`  

## dbt

- `profiles.yml.example` contains Athena configuration.  
- Models use `incremental_strategy: merge` with a 7-day sliding window for incremental updates.  
- `dbt docs generate` produces manifest/catalog/docs for auditing.

## Great Expectations

- Simple JSON expectation suites per domain in `great_expectations/expectations`.  
- Customize checkpoints or validation flows in Airflow as needed.

## Observability

- **Slack:** Set `slack_webhook_conn_id` in Airflow Variables.  
- **Email SLA:** Configure `ops_email` in Airflow Variables.  
- **OpenLineage:** Point `openlineage_endpoint` in Terraform to your backend (Marquez or another compatible service).

## Security and IAM

Minimum IAM policies for Glue and MWAA allow access to S3, Glue, Athena, and CloudWatch Logs.  
Adjust `iam:PassRole` and resource restrictions based on your governance model.

## Next Steps

- Replace `PythonOperator` with native operators (e.g., `AWSGlueCrawlerOperator`, `GreatExpectationsOperator`, `DbtRunOperator`).  
- Add unit tests for DAGs and Great Expectations suites.  
- Automate Z-Order via `ALTER TABLE ... ORDER BY` in Athena/Trino after data loads.

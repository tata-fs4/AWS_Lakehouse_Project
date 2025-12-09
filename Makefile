PROJECT=aws_lakehouse_project
TF_DIR=terraform

.PHONY: format terraform-init terraform-plan terraform-apply package-dbt upload-dags upload-dbt-docs generate-docs local-run

format:
terraform -chdir=$(TF_DIR) fmt
dbt format

terraform-init:
terraform -chdir=$(TF_DIR) init

terraform-plan:
terraform -chdir=$(TF_DIR) plan -out=tfplan

terraform-apply:
terraform -chdir=$(TF_DIR) apply tfplan

package-dbt:
dbt deps
dbt seed
dbt run --select staging+
dbt build --select marts+
dbt docs generate

upload-dags:
aws s3 sync airflow/dags s3://$${RAW_BUCKET}/dags

upload-dbt-docs:
aws s3 sync dbt/target s3://$${CURATED_BUCKET}/dbt_docs --delete

generate-docs:
dbt docs generate

local-run:
python local_runner.py --output-dir ./local_output

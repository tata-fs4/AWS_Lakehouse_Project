# AWS Lakehouse com Airflow + dbt

Este diretório contém um exemplo opinativo de lakehouse na AWS com ingestão via Airflow/MWAA, catálogo no Glue, transformações dbt e publicação em Athena/Parquet particionado por `dt` e `store_id` com Z-Order.

## Componentes
- **S3**: buckets `raw` e `curated` para landing e camadas processadas.
- **Glue**: database e crawlers por domínio (ERP, CRM, web e catálogo de produtos).
- **Airflow (MWAA)**: DAGs `ingest_{dominio}`, `validate_{dominio}`, `transform_{dominio}` e `publish_{dominio}` com retries, SLA handler e notificação Slack.
- **Great Expectations**: suites mínimas em `great_expectations/expectations` executadas na etapa `validate_*`.
- **dbt**: modelos de staging e fato `fct_daily_store_metrics` com manifest/docs gerados por `dbt docs generate` e armazenados no S3 `curated`.
- **Athena**: views e consultas sobre a camada transformada; particionamento por `dt`/`store_id` e Z-Order planejado no layout dos arquivos.
- **OpenLineage**: backend habilitado em MWAA para rastrear lineage das DAGs.
- **Terraform**: provisiona S3, Glue, MWAA e IAM.

## Estrutura
```
airflow/dags/           # DAGs e callbacks
samples/                # Dados simulados (ERP/CRM/web/products)
dbt/                    # Projeto dbt (modelos, seeds e manifest/docs via dbt)
great_expectations/     # Expectation suites básicas
terraform/              # Infra-as-code para AWS
Makefile                # Atalhos para deploy
README.md
```

## Dados simulados
Arquivos CSV/JSON em `samples/` refletem as fontes solicitadas: `erp_orders.csv`, `crm_leads.csv`, `web_events.json` e `products.csv`. Eles também são copiados para `dbt/seeds/` para execução local do dbt.

## Pipeline (DAG por domínio)
1. **ingest_{dominio}**: lê da fonte `s3://lakehouse-raw/<dominio>/` e dispara crawler Glue.
2. **validate_{dominio}**: executa checkpoint Great Expectations correspondente.
3. **transform_{dominio}**: roda `dbt build --select <dominio>` (incremental, partição `dt`/`store_id`, estratégia MERGE e Z-Order aplicado na escrita Parquet).
4. **publish_{dominio}**: cria/atualiza views Athena na camada curated e publica manifest/docs do dbt.

Os DAGs incluem `retries`, `on_failure_callback` (Slack), `sla_miss_callback` e `max_active_runs=1`. OpenLineage é configurado via `airflow_configuration_options` no MWAA.

## Deploy
Requisitos: Terraform >=1.5, AWS CLI configurado, dbt-athena-community plugin e acesso à conta AWS.

```bash
make terraform-init           # inicializa backend
make terraform-plan           # pré-visualiza mudanças (forneça TF_VAR_account_id etc.)
make terraform-apply          # cria buckets, Glue e MWAA
```

Após a infraestrutura, publique artefatos:
```bash
export RAW_BUCKET=$(terraform -chdir=terraform output -raw raw_bucket)
export CURATED_BUCKET=$(terraform -chdir=terraform output -raw curated_bucket)

make package-dbt              # seeds + staging + marts + docs
make upload-dags              # sincroniza DAGs para bucket fonte do MWAA
make upload-dbt-docs          # publica manifest/docs no bucket curated
```

### Execução local (QA)
- Dependências Python: pandas (já disponível no ambiente da imagem base).
- Rode um ciclo ponta-a-ponta usando os dados simulados:

```bash
cd aws_lakehouse_project
python local_runner.py --output-dir ./local_output
# ou make local-run
``` 

O comando valida os datasets com as suites Great Expectations em `great_expectations/expectations`, cria as tabelas de staging
equivalentes aos modelos dbt e materializa a `fct_daily_store_metrics` em `local_output/curated/` para conferência.

## dbt
- Arquivo `profiles.yml.example` traz configuração para Athena.
- Models em `dbt/models` usam `incremental_strategy: merge` e aplicam recorte de 7 dias em incrementais.
- `dbt docs generate` cria manifest/catalog/documentation para auditoria.

## Great Expectations
Suites JSON simples por domínio em `great_expectations/expectations`. Ajuste checkpoints/validações no Airflow conforme necessidade.

## Observabilidade
- Slack: defina `slack_webhook_conn_id` no Airflow Variable.
- Email SLA: defina `ops_email` no Airflow Variable.
- OpenLineage: configure `openlineage_endpoint` em Terraform para apontar para seu backend (Marquez ou serviço compatível).

## Segurança e IAM
Políticas mínimas para Glue/MWAA permitem acesso a S3, Glue, Athena e CloudWatch Logs. Ajuste `iam:PassRole` e restrições de recursos conforme governança.

## Próximos passos
- Substituir `PythonOperator` por operadores nativos (por exemplo, `AWSGlueCrawlerOperator`, `GreatExpectationsOperator`, `DbtRunOperator`).
- Adicionar testes unitários para DAGs e suites GE.
- Automatizar Z-Order com `ALTER TABLE ... ORDER BY` via Athena/Trino após load.

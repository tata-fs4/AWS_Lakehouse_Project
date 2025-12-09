"""
Airflow DAGs for ingesting, validating, transforming and publishing
Lakehouse data on AWS with OpenLineage enabled.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule
from airflow.utils.email import send_email
from airflow.models import Variable

try:
    from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
except ModuleNotFoundError:  # pragma: no cover - provider may not be installed locally
    SlackWebhookOperator = None

# Configuration shared across DAGs
DOMAINS = {
    "erp": {
        "source": "s3://lakehouse-raw/erp_orders/",
        "dataset": "erp_orders",
    },
    "crm": {
        "source": "s3://lakehouse-raw/crm_leads/",
        "dataset": "crm_leads",
    },
    "web": {
        "source": "s3://lakehouse-raw/web_events/",
        "dataset": "web_events",
    },
    "product": {
        "source": "s3://lakehouse-raw/products/",
        "dataset": "products",
    },
}

DEFAULT_ARGS = {
    "owner": "data-platform",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "sla": timedelta(minutes=60),
}


def _notify_slack(context):
    message = (
        f"DAG `{context['dag'].dag_id}` failed at task `{context['task_instance'].task_id}`. "
        f"Run id: {context['run_id']}."
    )
    if SlackWebhookOperator is None:
        print(message)
        return

    slack_conn_id = Variable.get("slack_webhook_conn_id", default_var=None)
    if not slack_conn_id:
        print("Slack connection id not set; skipping notification")
        return

    SlackWebhookOperator(
        task_id="post_to_slack_on_failure",
        http_conn_id=slack_conn_id,
        message=message,
    ).execute(context=context)


def _sla_callback(dag, task_list, blocking_task_list, slas, blocking_tis):
    message = f"SLA missed for DAG {dag.dag_id}. Tasks: {[s.task_id for s in slas]}"
    send_email(to=Variable.get("ops_email", default_var=""), subject="Airflow SLA missed", html_content=message)


def _ingest_to_glue(**context):
    domain = context["params"]["domain"]
    source = DOMAINS[domain]["source"]
    print(f"Trigger Glue crawler for domain {domain} reading {source}")


def _validate_with_ge(**context):
    domain = context["params"]["domain"]
    suite_name = f"ge.{domain}.expectations"
    print(f"Run Great Expectations checkpoint {suite_name}")


def _run_dbt(**context):
    domain = context["params"]["domain"]
    print(f"Run dbt build --select {domain} --vars 'domain:{domain}'")


def _publish_to_athena(**context):
    domain = context["params"]["domain"]
    print(f"Create/refresh Athena views for {domain}")


for domain in DOMAINS:
    dag_id = f"ingest_{domain}_lakehouse"

    with DAG(
        dag_id=dag_id,
        default_args=DEFAULT_ARGS,
        description=f"Lakehouse pipeline for {domain}",
        schedule_interval="0 */6 * * *",
        start_date=datetime(2024, 6, 1),
        catchup=False,
        on_failure_callback=_notify_slack,
        sla_miss_callback=_sla_callback,
        tags=["lakehouse", domain],
        max_active_runs=1,
    ) as dag:
        start = EmptyOperator(task_id="start")

        ingest = PythonOperator(
            task_id=f"ingest_{domain}",
            python_callable=_ingest_to_glue,
            params={"domain": domain},
        )

        validate = PythonOperator(
            task_id=f"validate_{domain}",
            python_callable=_validate_with_ge,
            params={"domain": domain},
        )

        transform = PythonOperator(
            task_id=f"transform_{domain}",
            python_callable=_run_dbt,
            params={"domain": domain},
        )

        publish = PythonOperator(
            task_id=f"publish_{domain}",
            python_callable=_publish_to_athena,
            params={"domain": domain},
            trigger_rule=TriggerRule.ALL_SUCCESS,
        )

        end = EmptyOperator(task_id="end", trigger_rule=TriggerRule.ALL_DONE)

        start >> ingest >> validate >> transform >> publish >> end

    globals()[dag_id] = dag

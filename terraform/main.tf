terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  project = "lakehouse"
}

resource "aws_s3_bucket" "raw" {
  bucket = "${local.project}-raw-${var.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket" "curated" {
  bucket = "${local.project}-curated-${var.account_id}"
  force_destroy = true
}

resource "aws_glue_catalog_database" "lakehouse" {
  name = "${local.project}_raw"
}

resource "aws_glue_crawler" "domains" {
  for_each = var.domains
  name          = "${local.project}-${each.key}-crawler"
  database_name = aws_glue_catalog_database.lakehouse.name
  role          = aws_iam_role.glue.arn
  s3_target {
    path = "s3://${aws_s3_bucket.raw.bucket}/${each.value.prefix}/"
  }
}

resource "aws_iam_role" "glue" {
  name               = "${local.project}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy" "glue_access" {
  name   = "${local.project}-glue-access"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_policy.json
}

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "glue_policy" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket", "s3:PutObject"]
    resources = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*", aws_s3_bucket.curated.arn, "${aws_s3_bucket.curated.arn}/*"]
  }

  statement {
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:*:*:log-group:/aws-glue/*"]
  }
}

resource "aws_mwaa_environment" "this" {
  name               = "${local.project}-mwaa"
  environment_class  = "mw1.small"
  airflow_version    = "2.9.0"
  dag_s3_path        = "dags"
  source_bucket_arn  = aws_s3_bucket.raw.arn
  execution_role_arn = aws_iam_role.mwaa.arn
  webserver_access_mode = "PUBLIC_ONLY"

  network_configuration {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.security_group_id]
  }

  logging_configuration {
    task_logs {
      enabled   = true
      log_level = "INFO"
    }
    dag_processing_logs { enabled = true }
    webserver_logs      { enabled = true }
    worker_logs         { enabled = true }
    scheduler_logs      { enabled = true }
  }

  airflow_configuration_options = {
    "core.lazy_load_plugins"                    = "False"
    "core.store_serialized_dags"                = "True"
    "lineage.backend"                           = "openlineage.airflow.backend.OpenLineageBackend"
    "openlineage.transport"                    = jsonencode({"type":"http", "url": var.openlineage_endpoint, "endpoint": "/api/v1/lineage"})
    "openlineage.namespace"                    = "lakehouse"
    "openlineage.transport.timeout"            = "10"
  }
}

resource "aws_iam_role" "mwaa" {
  name               = "${local.project}-mwaa"
  assume_role_policy = data.aws_iam_policy_document.mwaa_assume.json
}

resource "aws_iam_role_policy_attachment" "mwaa_basic" {
  role       = aws_iam_role.mwaa.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonMWAAFullConsoleAccess"
}

resource "aws_iam_role_policy" "mwaa_extra" {
  name   = "${local.project}-mwaa-extra"
  role   = aws_iam_role.mwaa.id
  policy = data.aws_iam_policy_document.mwaa_policy.json
}

data "aws_iam_policy_document" "mwaa_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["airflow.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "mwaa_policy" {
  statement {
    actions   = ["s3:*", "glue:*", "athena:*", "iam:PassRole"]
    resources = ["*"]
  }
}

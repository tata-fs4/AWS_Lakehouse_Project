{{ config(materialized='view') }}

select
  event_id,
  visitor_id,
  store_id,
  cast(dt as date) as dt,
  page,
  event_type,
  metadata
from {{ source('aws_lakehouse', 'web_events') }}

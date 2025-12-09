{{ config(materialized='view') }}

select
  lead_id,
  name,
  email,
  source,
  status,
  store_id,
  cast(dt as date) as dt
from {{ source('aws_lakehouse', 'crm_leads') }}

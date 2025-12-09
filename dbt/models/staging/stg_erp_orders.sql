{{ config(materialized='view') }}

select
  cast(order_id as integer) as order_id,
  customer_id,
  store_id,
  cast(dt as date) as dt,
  cast(order_value as numeric(12,2)) as order_value,
  status
from {{ source('aws_lakehouse', 'erp_orders') }}

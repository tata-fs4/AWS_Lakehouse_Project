{{ config(materialized='view') }}

select
  product_id,
  name,
  category,
  cast(price as numeric(12,2)) as price,
  active,
  store_id,
  cast(dt as date) as dt
from {{ source('aws_lakehouse', 'products') }}

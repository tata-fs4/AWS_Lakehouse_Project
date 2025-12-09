{{ config(
    materialized='incremental',
    unique_key=['store_id', 'dt'],
    incremental_strategy='merge'
) }}

with orders as (
  select store_id, dt, sum(order_value) as revenue, count(*) as order_count
  from {{ ref('stg_erp_orders') }}
  group by 1,2
),
leads as (
  select store_id, dt, count(*) filter (where status = 'converted') as converted_leads
  from {{ ref('stg_crm_leads') }}
  group by 1,2
),
web as (
  select store_id, dt, count(*) as sessions
  from {{ ref('stg_web_events') }}
  group by 1,2
)

select
  coalesce(o.store_id, l.store_id, w.store_id) as store_id,
  coalesce(o.dt, l.dt, w.dt) as dt,
  coalesce(o.revenue, 0) as revenue,
  coalesce(o.order_count, 0) as order_count,
  coalesce(l.converted_leads, 0) as converted_leads,
  coalesce(w.sessions, 0) as sessions
from orders o
full outer join leads l using (store_id, dt)
full outer join web w using (store_id, dt)

{% if is_incremental() %}
where coalesce(o.dt, l.dt, w.dt) >= dateadd(day, -7, current_date)
{% endif %}

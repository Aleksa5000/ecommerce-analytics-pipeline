-- Monthly acquisition cohorts (month of first completed order) x months since first order.
-- The grid is complete: months without orders show 0 active customers, not a missing row.
with first_orders as (
    select customer_id, country, order_month as cohort_month
    from {{ ref('int_orders') }}
    where is_first_order
),
activity as (
    select distinct customer_id, order_month from {{ ref('int_orders') }}
),
cohort_sizes as (
    select cohort_month, country, count(*) as cohort_size
    from first_orders
    group by cohort_month, country
),
last_month as (
    select max(order_month) as last_month from {{ ref('int_orders') }}
),
grid as (
    select
        s.cohort_month,
        s.country,
        s.cohort_size,
        unnest(range(0, date_diff('month', s.cohort_month, l.last_month) + 1)) as month_number
    from cohort_sizes s
    cross join last_month l
),
active as (
    select
        f.cohort_month,
        f.country,
        date_diff('month', f.cohort_month, a.order_month) as month_number,
        count(distinct a.customer_id) as active_customers
    from first_orders f
    join activity a on a.customer_id = f.customer_id
    group by f.cohort_month, f.country, date_diff('month', f.cohort_month, a.order_month)
)
select
    g.cohort_month,
    g.country,
    g.month_number,
    g.cohort_size,
    coalesce(a.active_customers, 0) as active_customers
from grid g
left join active a
    on a.cohort_month = g.cohort_month and a.country = g.country and a.month_number = g.month_number

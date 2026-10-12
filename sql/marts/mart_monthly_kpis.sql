-- Grain: month x country (customers have exactly one country, so every column is additive
-- across countries). AOV = gross revenue / orders (before refunds).
with m as (
    select
        order_month,
        country,
        count(*) as orders,
        count(distinct customer_id) as customers,
        count(distinct customer_id) filter (where is_first_order) as new_customers,
        sum(units) as units,
        sum(gross_eur) as gross_eur,
        sum(refund_eur) as refund_eur,
        sum(net_eur) as net_eur
    from {{ ref('int_orders') }}
    group by order_month, country
)
select
    order_month,
    country,
    orders,
    customers,
    new_customers,
    customers - new_customers as returning_customers,
    units,
    round(gross_eur, 2) as gross_eur,
    round(refund_eur, 2) as refund_eur,
    round(net_eur, 2) as net_eur,
    round(gross_eur / orders, 2) as aov_eur
from m

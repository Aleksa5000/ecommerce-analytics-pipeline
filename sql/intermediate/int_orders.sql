-- One row per completed order, with the customer's running order number.
with orders as (
    select
        order_id,
        customer_id,
        any_value(country) as country,
        order_date,
        order_month,
        count(*) as line_count,
        sum(quantity) as units,
        sum(gross_eur) as gross_eur,
        sum(refund_eur) as refund_eur,
        sum(net_eur) as net_eur
    from {{ ref('int_order_lines') }}
    group by order_id, customer_id, order_date, order_month
)
select
    *,
    row_number() over (partition by customer_id order by order_date, order_id) as customer_order_number,
    row_number() over (partition by customer_id order by order_date, order_id) = 1 as is_first_order
from orders

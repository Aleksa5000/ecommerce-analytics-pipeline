-- Fact table behind every filterable dashboard view: one row per completed order line.
select
    l.*,
    o.customer_order_number,
    o.is_first_order
from {{ ref('int_order_lines') }} l
join {{ ref('int_orders') }} o using (order_id)

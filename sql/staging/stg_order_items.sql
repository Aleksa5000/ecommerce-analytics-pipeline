select
    order_item_id::integer as order_item_id,
    order_id::integer as order_id,
    product_id::integer as product_id,
    quantity::integer as quantity,
    unit_price::decimal(12, 2) as unit_price,
    discount_pct::decimal(4, 3) as discount_pct
from {{ source('order_items') }}

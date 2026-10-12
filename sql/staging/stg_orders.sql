select
    order_id::integer as order_id,
    customer_id::integer as customer_id,
    order_date::date as order_date,
    currency,
    status
from {{ source('orders') }}

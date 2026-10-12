select
    return_id::integer as return_id,
    order_item_id::integer as order_item_id,
    return_date::date as return_date,
    reason
from {{ source('returns') }}

select
    product_id::integer as product_id,
    trim(product_name) as product_name,
    category,
    list_price_eur::decimal(10, 2) as list_price_eur
from {{ source('products') }}

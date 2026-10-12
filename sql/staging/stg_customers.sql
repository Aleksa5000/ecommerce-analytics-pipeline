select
    customer_id::integer as customer_id,
    lower(trim(email)) as email,
    upper(trim(country)) as country,
    signup_date::date as signup_date,
    acquisition_channel
from {{ source('customers') }}

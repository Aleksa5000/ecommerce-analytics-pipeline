select
    date_trunc('month', month::date)::date as rate_month,
    currency,
    eur_per_unit::double as eur_per_unit
from {{ source('fx_rates') }}

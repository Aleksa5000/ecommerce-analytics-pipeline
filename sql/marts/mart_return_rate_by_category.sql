-- Grain: month x country x category. Return rate = returned lines / lines
-- (recompute from the counts when aggregating, never average the rate).
select
    order_month,
    country,
    category,
    count(*) as order_lines,
    count(*) filter (where is_returned) as returned_lines,
    sum(quantity) as units,
    round(sum(gross_eur), 2) as gross_eur,
    round(sum(refund_eur), 2) as refund_eur,
    round(count(*) filter (where is_returned) * 1.0 / count(*), 4) as return_rate
from {{ ref('fct_order_lines') }}
group by order_month, country, category

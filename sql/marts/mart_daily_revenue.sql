-- Grain: day x country x category. `orders` counts distinct orders containing the category,
-- so it is additive over days and countries but NOT over categories.
select
    order_date,
    country,
    category,
    count(distinct order_id) as orders,
    sum(quantity) as units,
    round(sum(gross_eur), 2) as gross_eur,
    round(sum(refund_eur), 2) as refund_eur,
    round(sum(net_eur), 2) as net_eur
from {{ ref('fct_order_lines') }}
group by order_date, country, category

-- All-time product ranking by net revenue (EUR).
select
    rank() over (order by sum(net_eur) desc) as revenue_rank,
    product_id,
    product_name,
    category,
    sum(quantity) as units,
    count(*) as order_lines,
    count(*) filter (where is_returned) as returned_lines,
    round(count(*) filter (where is_returned) * 1.0 / count(*), 4) as return_rate,
    round(sum(gross_eur), 2) as gross_eur,
    round(sum(net_eur), 2) as net_eur
from {{ ref('fct_order_lines') }}
group by product_id, product_name, category

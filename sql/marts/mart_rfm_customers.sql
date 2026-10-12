-- RFM snapshot as of (last order date + 1 day). Recency and monetary are quintile scores,
-- frequency uses fixed thresholds (1 / 2 / 3 / 4-5 / 6+ orders) because order counts are heavily tied.
-- Segments are defined on R and F only; M is a ranking score (per customer, not used in segments).
with snapshot as (
    select max(order_date) + 1 as as_of from {{ ref('int_orders') }}
),
agg as (
    select
        customer_id,
        any_value(country) as country,
        max(order_date) as last_order_date,
        count(*) as frequency,
        round(sum(net_eur), 2) as monetary_eur
    from {{ ref('int_orders') }}
    group by customer_id
),
ranked as (
    select
        a.*,
        date_diff('day', a.last_order_date, s.as_of) as recency_days,
        ntile(5) over (order by date_diff('day', a.last_order_date, s.as_of) desc, a.customer_id) as r_tile,
        case
            when a.frequency >= 6 then 5
            when a.frequency >= 4 then 4
            else a.frequency
        end as f_score,
        ntile(5) over (order by a.monetary_eur, a.customer_id) as m_score
    from agg a
    cross join snapshot s
),
scored as (
    -- equal recency gets one R score (the lowest tile in the tie), so customer_id never decides it
    select * exclude (r_tile), min(r_tile) over (partition by recency_days) as r_score
    from ranked
)
select
    customer_id, country, last_order_date, recency_days, frequency, monetary_eur,
    r_score, f_score, m_score,
    case
        when r_score >= 4 and f_score >= 4 then 'Champions'
        when r_score >= 3 and f_score >= 3 then 'Loyal'
        when r_score >= 4 and f_score = 1 then 'New Customers'
        when r_score >= 4 then 'Potential Loyalists'
        when r_score <= 2 and f_score >= 3 then 'At Risk'
        when r_score = 3 then 'Needs Attention'
        when r_score = 2 then 'Hibernating'
        else 'Lost'
    end as segment
from scored

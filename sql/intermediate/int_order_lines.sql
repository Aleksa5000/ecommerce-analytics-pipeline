-- One row per line of a COMPLETED order, converted to EUR at the order month's FX rate.
-- Refunds are recognised on the order date (full refund of the line when it was returned).
with priced as (
    select
        i.order_item_id,
        i.order_id,
        o.customer_id,
        c.country,
        i.product_id,
        p.product_name,
        p.category,
        o.order_date,
        date_trunc('month', o.order_date)::date as order_month,
        o.currency,
        i.quantity,
        i.unit_price,
        i.discount_pct,
        i.quantity * i.unit_price * (1 - i.discount_pct) as gross_local,
        i.quantity * i.unit_price * (1 - i.discount_pct) * fx.eur_per_unit as gross_eur_raw
    from {{ ref('stg_order_items') }} i
    join {{ ref('stg_orders') }} o on o.order_id = i.order_id
    join {{ ref('stg_customers') }} c on c.customer_id = o.customer_id
    join {{ ref('stg_products') }} p on p.product_id = i.product_id
    join {{ ref('stg_fx_rates') }} fx
        on fx.currency = o.currency and fx.rate_month = date_trunc('month', o.order_date)
    where o.status = 'completed'
)
select
    pr.order_item_id, pr.order_id, pr.customer_id, pr.country, pr.product_id, pr.product_name,
    pr.category, pr.order_date, pr.order_month, pr.currency, pr.quantity, pr.unit_price,
    pr.discount_pct,
    round(pr.gross_local, 2) as gross_local,
    round(pr.gross_eur_raw, 2) as gross_eur,
    r.order_item_id is not null as is_returned,
    r.return_date,
    case when r.order_item_id is not null then round(pr.gross_eur_raw, 2) else 0 end as refund_eur,
    round(pr.gross_eur_raw, 2)
        - case when r.order_item_id is not null then round(pr.gross_eur_raw, 2) else 0 end as net_eur
from priced pr
left join {{ ref('stg_returns') }} r on r.order_item_id = pr.order_item_id

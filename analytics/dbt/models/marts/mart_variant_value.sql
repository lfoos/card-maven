-- Shared market value per card variant and condition over a trailing window.
-- Per-collector estimates (which include private manual comps) are computed
-- online by the API; this is the market-wide view used for trends.
with windowed as (
    select *
    from {{ ref('int_sales_graded') }}
    where sold_on > {{ as_of_date() }} - {{ var('value_window_days') }}
        and sold_on <= {{ as_of_date() }}
)

select
    md5(variant_id::text || '|' || condition_bucket || '|' || currency) as variant_value_id,
    variant_id,
    condition_bucket,
    currency,
    count(*)::integer as sales_count,
    (percentile_cont(0.5) within group (order by price_minor))::numeric(14, 1) as median_price_minor,
    min(price_minor) as min_price_minor,
    max(price_minor) as max_price_minor,
    max(sold_at) as latest_sold_at,
    {{ as_of_date() }} as as_of_date
from windowed
group by variant_id, condition_bucket, currency

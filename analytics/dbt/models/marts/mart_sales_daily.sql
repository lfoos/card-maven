-- Daily sales volume and median price per set: groundwork for trends (Phase 5).
select
    md5(variants.set_id::text || '|' || sales.sold_on::text || '|' || sales.currency) as set_day_id,
    variants.sport,
    variants.set_id,
    variants.year,
    variants.set_name,
    sales.sold_on,
    sales.currency,
    count(*)::integer as sales_count,
    sum(sales.price_minor)::bigint as total_price_minor,
    (percentile_cont(0.5) within group (order by sales.price_minor))::numeric(14, 1) as median_price_minor
from {{ ref('int_sales_graded') }} as sales
inner join {{ ref('stg_catalog__variants') }} as variants
    on variants.variant_id = sales.variant_id
group by variants.sport, variants.set_id, variants.year, variants.set_name, sales.sold_on, sales.currency

-- Sales eligible for shared analytics: analytics-licensed sources, matched to
-- a card variant, and shared (private manual comps are excluded).
select
    sale.id as sale_id,
    sale.variant_id,
    sale.source_code,
    sale.sold_at,
    (sale.sold_at at time zone 'utc')::date as sold_on,
    sale.price_minor,
    sale.currency,
    sale.condition,
    sale.grader,
    sale.grade,
    sale.sale_type
from {{ source('app', 'sale') }} as sale
inner join {{ source('app', 'market_source') }} as market_source
    on market_source.code = sale.source_code
where market_source.license = 'analytics'
    and sale.variant_id is not null
    and sale.submitted_by is null

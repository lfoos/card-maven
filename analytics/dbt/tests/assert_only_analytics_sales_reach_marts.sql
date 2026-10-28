-- ADR-0009: display-only sources (eBay) must never feed analytics. Every sale
-- behind the marts must come from an `analytics` source, be matched, and be
-- shared. Returns offending rows (the test passes when there are none).
select graded.sale_id, graded.source_code, market_source.license, sale.submitted_by
from {{ ref('int_sales_graded') }} as graded
inner join {{ source('app', 'sale') }} as sale on sale.id = graded.sale_id
left join {{ source('app', 'market_source') }} as market_source
    on market_source.code = graded.source_code
where market_source.license is distinct from 'analytics'
    or sale.submitted_by is not null
    or sale.variant_id is null

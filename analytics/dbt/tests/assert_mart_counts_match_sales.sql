-- The value mart accounts for every eligible sale in its window exactly once.
with expected as (
    select count(*) as n
    from {{ ref('int_sales_graded') }}
    where sold_on > {{ as_of_date() }} - {{ var('value_window_days') }}
        and sold_on <= {{ as_of_date() }}
),
actual as (
    select coalesce(sum(sales_count), 0) as n from {{ ref('mart_variant_value') }}
)
select expected.n as expected, actual.n as actual
from expected cross join actual
where expected.n <> actual.n

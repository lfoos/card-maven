select
    sales.*,
    {{ condition_bucket('sales.condition', 'sales.grader', 'sales.grade') }} as condition_bucket
from {{ ref('stg_market__sales') }} as sales

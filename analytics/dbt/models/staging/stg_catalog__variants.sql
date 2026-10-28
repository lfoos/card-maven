select
    variant.id as variant_id,
    card.id as card_id,
    card_set.id as set_id,
    card_set.sport_code as sport,
    card_set.brand_slug as brand,
    card_set.year,
    card_set.name as set_name,
    card.card_number,
    card.name as card_name,
    parallel.name as parallel_name,
    parallel.print_run
from {{ source('app', 'card_variant') }} as variant
inner join {{ source('app', 'card') }} as card on card.id = variant.card_id
inner join {{ source('app', 'card_set') }} as card_set on card_set.id = card.set_id
inner join {{ source('app', 'parallel') }} as parallel on parallel.id = variant.parallel_id

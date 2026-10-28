# 0009. Market data is licensed per source; eBay data is display-only

**Status:** Accepted · **Date:** 2026-10-27

## Context
Card Maven's comps, estimated values, and trends are only as legitimate as the data's license. eBay's [API License Agreement](https://www.edp.ebay.com/join/api-license-agreement) (reviewed 2026-10-27; not legal advice):

- **§9.5:** forbids using eBay content "to suggest or model prices".
- **§8.1(d)(1):** requires written permission to derive statistics such as "average selling price … for any eBay category".
- **§8.5.2–8.5.3:** restricts market-trend, pricing, and sales-volume data from Restricted APIs (likely including Marketplace Insights) in pricing tools without express consent.
- **§8.1(b–c):** displayed listing data must be at most 6 hours stale, and deleted once no longer public.
- **§9.10:** forbids training AI on eBay content.

## Decision
- **Every market source has a license.** Each `market_source` row carries `license` (`analytics` | `display_only`) and `max_age_hours`.
- **Only `analytics` sources feed comps, estimated values, dbt marts, and trends.** This is enforced at ingestion (a display-only source can't create sales), in queries, and by a dbt test.
- **eBay Browse is `display_only` with `max_age_hours = 6`.** Card Maven shows current asks with affiliate links and their age, and purges listings that weren't re-observed in time.
- **No AI use of eBay content.** eBay titles and images are never used to train or fine-tune models, or to build embeddings (relevant to Phase 3).
- **Upgrades are a data change.** A source becomes `analytics` only with written permission from its owner (eBay, or a licensed provider). That's a row in config, not a code change.

## Consequences
- Until an analytics-licensed source exists in production, estimated values come only from collectors' own manual comps (private) and dev fixtures. The UI says so rather than showing a misleading number.
- Phase 5 trends will cover analytics-licensed data only. Getting eBay's written consent, or licensing a provider, is a business prerequisite for market-wide trends.
- Marketplace Insights, if approved, enters as `display_only` (sold comps shown, not modelled) unless eBay's consent covers valuation.

## Alternatives considered
- **Treat eBay data as analytics:** fastest path to estimates and trends, but contrary to the terms quoted above.
- **No eBay at all:** loses the legitimate, useful "current asks" view and the affiliate revenue the Insights application depends on.

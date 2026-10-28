# 0003: Market data pipeline: Security review

**Verdict: no blocking findings.**

## Threats considered and mitigations

| Threat | Mitigation | Verified by |
|---|---|---|
| **eBay license breach.** Using listing data for estimates, statistics, or AI; or showing stale data. | Display-only license enforced at ingestion, query, and dbt layers. Asks are shown only while under 6 h old, and the hourly purge deletes them after that (or once ended). No listing data in events or marts. | Ingestion, comps, purge, and dbt tests. |
| **Secret exposure (eBay keys).** | Keys come from environment variables (`SecretStr`, never logged), never from the repo. In Kubernetes, only the market-worker Deployment receives them (optional `secretKeyRef`), not the API or CronJobs. The deploy guard refuses the fixture source outside local/test. | Config tests; Helm template. |
| **Malicious links.** `javascript:` or `data:` URLs from a manual sale or a source. | Manual URLs must be http(s). The API drops any non-http(s) URL before responding. Links open with `noopener noreferrer`; affiliate links add `sponsored`. | API and web tests. |
| **Private comps leaking.** | Manual sales carry `submitted_by` and are visible only to that collector. They're excluded from dbt marts and deletable only by their author. | Comps, API, and dbt singular tests. |
| **Job enumeration / requester disclosure.** | Variant jobs are visible only to holders of the card; tracked-set jobs are never exposed. The response omits `requested_by` and per-source stats. Unexpected adapter errors show a generic message, with details in logs. | API and ingestion tests. |
| **Quota exhaustion and abuse.** | Refresh is limited to 10/min per user, plus per-card dedupe (15 min). Manual sales: 200 per request, 60 writes/min, at most 1,000 per collector per card. The browser refuses CSV files over 1 MB, and the API body limit is 1 MB. | Rate-limit, cap, and web tests. |
| **Poison messages.** | Undecodable or invalid events go to `<topic>.dlq` without retry, and the consumer never commits past a message it couldn't park. | Consumer tests. |
| **Container hardening.** | The new Deployment and CronJobs reuse the chart's non-root, read-only root filesystem, drop-all-capabilities defaults. dbt writes only to an emptyDir `/tmp`. | Helm render + kubeconform in CI. |

## Accepted risks and follow-ups

1. **Global eBay quota (Phase 6).** Per-user limits don't bound the total across users. Add a shared token bucket before production keys and wider use.
2. **dbt database role (Phase 6).** dbt uses the application's credentials. With RDS, give it a role that can read `public` and write only `analytics`.
3. **FTC/EPN disclosure.** The listings section states that links may earn a commission. Legal should review the wording before launch.
4. **Carried over:** shared rate-limit storage, web CSP, and SHA-pinned Actions (Phase 6); EXIF stripping (Phase 3).

# HomeAksoria Phase 0 final audit

| Original brief | Status and evidence |
| --- | --- |
| 1. Backend goal | Multi-product Django API and admin. No storefront UI. |
| 2. Technologies | Python 3.12, Django 5.2, DRF, PostgreSQL, Redis, Celery, SimpleJWT, drf-spectacular, Pillow, django-filter and Docker. |
| 3. App architecture | Modular apps, services and selectors. Orders and payments are app boundaries for later phases. |
| 4. Accounts | Phone registration/login, profile, photos, password change and JWT rotation/blacklisting. Phone proof and recovery delivery are extension interfaces only. |
| 5. Products | Multiple products, galleries, stock, price, discount, history, and administration. Variant models are deferred. |
| 6. Categories | Nested categories, ancestor visibility, cycle prevention and behavioral category suggestions. |
| 7. Analytics | View deduplication, unique estimate, guest/account split, rolling windows and staff reports. |
| 8. Favorites | One favorite per user/product, add/remove/list, counts and ranking. |
| 9. Ranking | Sorting by popularity, views, favorites, price, discount, freshness and weighted score. Sales ranking awaits order data. |
| 10. Recommendation | Guest and personalized products/categories, similar/related products, configurable policy, no external inference. |
| 11. Search | Persian normalization, autocomplete, indexed FTS and Trigram, popular phrases, private recent history. |
| 12. Reviews | Owner writes, moderation, public ratings and manager replies. Reply model has a parent reference; public writing stays top-level. |
| 13. Cart and orders | Phase 1, outside audit implementation scope. |
| 14. Payments | Phase 2, outside audit implementation scope. There is no gateway, payment service or transaction data. |
| 15. SEO | Product metadata and fallbacks, Open Graph, Twitter, Canonical, Product/Offer JSON-LD, Sitemap and robots.txt. |
| 16. Dashboard | Private profile, favorites, reviews, search, views and notifications. Orders, addresses and payments follow their phases. |
| 17. Admin API | Customer search and status, catalog/images/SEO, moderation/replies, traffic/popularity, ranking and recommendation policy, roles and audit log. Sales and transaction reporting await live models. |
| 18. API structure | Versioned endpoint families plus schema, Swagger, ReDoc, Sitemap and robots.txt. |
| 19. Performance/security | SQL bounds and indexes, related-object loading, Redis throttling, account ownership, JWT revocation, image validation and transactional writes. Some popular feeds aggregate live counts. |
| 20. Docker | Compose services for Django, PostgreSQL, Redis, worker and beat, plus init and gateway. One-command start with generated local secrets. |
| 21. Docs and testing | OpenAPI and executable tests for implemented domains. Cart/order/payment mock tests follow those modules. |
| 22. Implementation rules | Scoped migrations, vendor-specific search migration, tests and README; no production credentials in versioned source. |
| 23. Phase order | Audit changes scoped to Phase 0. |

## Findings

| Priority | Finding | Resolution |
| --- | --- | --- |
| High | Customer administration, managed roles and audit visibility were incomplete. | Implemented permission-scoped customer and audit APIs and five managed role names. Staff accounts cannot be modified through the customer endpoint. |
| High | A full-row profile save could overwrite concurrent changes to account state. Old tokens also needed explicit invalidation on reactivation. | Profile saves only changed fields under a lock. Customer status transitions invalidate old access and refresh tokens and audit the change. |
| High | Docker startup and deployable static/media serving were missing. | Added Compose build, startup script, initialization, gateway, worker and beat. The local configuration binds to loopback. |
| Medium | Recommendation knobs and catalog reports were not exposed to administrators. | Added permission-scoped configuration and traffic reports and independent weighted catalog ordering. |
| Medium | Images could have a misleading extension. | Require decoded format to match extension, retain size/pixel validation, and limit request size at the gateway. |
| Medium | Auth/admin responses had inconsistent cache protections. | Added private no-store headers at the relevant API prefixes. |
| Medium | Password recovery and phone ownership verification have interfaces but no verified delivery flow. | Open. A verified identity delivery channel is required before enabling recovery and ownership verification. |
| Medium | Popularity feeds aggregate live engagement, and no large-catalog load benchmark exists. | Open. N+1 regressions are covered by query-count tests; capacity at production scale remains unmeasured. |
| Low | Custom catalog ordering could leave unstable ties across pages. | Added a stable primary-key tie breaker. |
| Low | Guest unique counts are approximate and DRF throttles are best-effort under concurrency. | Open. These limitations remain part of the Phase 0 design. |

No Critical defect was confirmed in the tested Phase 0 flows. This audit did
not include a production load test or a third-party dependency audit.

## Verification

- 63 tests passed inside the Compose web container against PostgreSQL 17 and Redis 7.
- Migrations had no pending operations and model drift was empty. The audit added
  account session version and recommendation policy migrations.
- OpenAPI validation completed with warnings treated as errors. Swagger, ReDoc,
  the schema route, admin static CSS, Sitemap and robots.txt returned HTTP 200
  through the gateway.
- Django's production deployment checks passed with HTTPS, HSTS and secure-cookie
  settings enabled for the check. The verified running Compose profile used localhost HTTP.
- Redis-backed login throttling returned HTTP 429. The gateway returned HTTP 413 for
  an oversized request. CORS sent the allow-origin header for the configured origin
  only. Celery worker responded to ping and Beat started with Redis.
- PostgreSQL EXPLAIN probes confirmed eligibility of the FTS/Trigram, notification,
  public review, and account view indexes with sequential scans disabled for the
  probe. Query-count tests covered gallery and reply loading on paginated lists.
- This runner needed its trusted proxy CA as a BuildKit secret. Alpine database
  and cache images allowed the complete stack to start in the runner's limited
  Docker storage.


## Phase 1 inventory follow-up

The Phase 0 audit above is historical. Phase 1 now includes owned addresses,
cart, order snapshots, PostgreSQL-locked stock reservation, cancellation and
background expiration. The migration records opening balances without altering
stock and leaves orders created before reservation tracking readable. A
terminal inventory movement is unique per reservation. Admin and Product
Manager have inventory adjustment permissions. Order Manager receives
read-only order and ledger access. Checkout and cancellation reconcile overdue
holds on the request path. Payment verification and any transition to paid
remain outside this step.

## Phase 1 high-severity remediation

The remediation adds revision-checked absolute inventory writes and separates
PostgreSQL bootstrap, migration and runtime. See `AUDIT_PHASE1_REMEDIATION.md`
for exact verification and remaining limits.

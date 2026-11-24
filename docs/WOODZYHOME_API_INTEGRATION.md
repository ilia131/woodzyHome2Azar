# WoodZyHome Backend API Integration

Django and the generated OpenAPI document are the contract. The table counts distinct HTTP method and path pairs under `/api/v1/`. A call is counted as connected when an existing storefront or management flow calls it. Contract coverage is separate from end-to-end assertions and live deployment.

## Coverage

| Domain | Available | Called by UI | Without a separate UI call |
|---|---:|---:|---:|
| addresses | 5 | 4 | 1 |
| admin | 52 | 39 | 13 |
| auth | 11 | 11 | 0 |
| cart | 4 | 4 | 0 |
| categories | 4 | 4 | 0 |
| dashboard | 6 | 5 | 1 |
| favorites | 4 | 4 | 0 |
| orders | 4 | 4 | 0 |
| payments | 7 | 4 | 3 |
| products | 12 | 11 | 1 |
| recommendations | 1 | 1 | 0 |
| reviews | 2 | 2 | 0 |
| search | 4 | 3 | 1 |
| store | 3 | 3 | 0 |
| **Total** | **119** | **99** | **20** |

The uncalled operations include aliases for data already retrieved by list or status operations, the provider-to-server payment callback, mock-page GET, and admin operations still lacking UI (refunds and category/SEO deletion). The advertised product DELETE rejects deletion by policy; the editor deactivates catalog items to preserve history. This inventory marks only calls present in the UI. The dedicated recent-search API and dashboard favorites API are represented in the UI through their corresponding dashboard search and storefront favorites list operations.

## Changes and runtime behavior

- Login stores both JWTs in secure HttpOnly cookies in production. Renewal is an explicit action on the sign-in screen. The backend rotates the refresh token, and logout asks the backend to blacklist it. Django retains authorization for all private operations.
- Added `GET favorites/status/?ids=…` with authenticated per-caller filtering and private no-store caching. Product cards use a batched lookup; the detail page and favorites list use the same persisted state.
- Added `GET products/best-selling/`. Ranking uses quantities in completed orders. Popular products, most-viewed products and discounts retain independent feeds.
- The search screen combines the existing debounced suggestions, paginated results and popular-query feed. Authenticated requests also feed Django's search history and product-view history. Category detail, children and recommended categories use their respective endpoints.
- The dashboard reads orders, payments and addresses as well as profile and activity. Reviews show ratings and shop replies. Admin adds gallery metadata edits, product history and views, popular reports and ranking weights alongside the existing policy settings.
- Production requires a Next.js-reachable `DJANGO_API_URL`. `DJANGO_MEDIA_URL` is optional for a separate public media address. Demo data requires explicit development opt-in. `WOODZY_TEST_PAYMENTS=1` is for the isolated mock flow, and Django still validates provider availability.
- SMTP delivery and real payment enablement depend on external configuration. Physical showroom and editorial media are supplied separately from catalog API data. Session renewal is user-initiated. Public ingress, gateway credentials and browser reachability of production media were outside the isolated run.

## Route coverage

All 27 intended page types are exercised by the browser route/RTL and viewport checks. The suite also has separate workflow tests. Its route check alone does not assert every individual mutation.

| Page group | Routes and main integration |
|---|---|
| Storefront (8) | `/`, `/products`, `/products/[slug]`, `/categories`, `/categories/[slug]`, `/search`, `/favorites`, `/about`. Catalog, recommendations, reviews, search, favorites, contact and newsletter. |
| Account (6) | `/account/auth`, `/account/recovery`, `/account/dashboard`, `/account/profile`, `/account/orders`, `/account/activity`. JWT/session management, verified recovery, personal dashboard, addresses, history and reviews. |
| Checkout (4) | `/checkout/cart`, `/checkout/details`, `/checkout/payment`, `/checkout/result`. Server totals, order creation, explicit test gateway and status lookup. |
| Administration (9) | `/admin/overview`, `/admin/products`, `/admin/editor`, `/admin/categories`, `/admin/inventory`, `/admin/orders`, `/admin/customers`, `/admin/payments`, `/admin/settings`. Protected management API, reports and configuration. |

## Endpoint inventory

Request/response schemas and security schemes are available from Django at `/api/schema/` and `/api/docs/`. View classes, serializers and permissions are referenced from [the API router](../config/urls.py).

| Path under /api/v1/ | UI method | Method without separate UI call |
|---|---|---|
| `addresses/` | GET, POST | — |
| `addresses/{id}/` | PATCH, DELETE | GET |
| `admin/audit-logs/` | GET | — |
| `admin/audit-logs/{id}/` | — | GET |
| `admin/categories/` | GET, POST | — |
| `admin/categories/{id}/` | PATCH | GET, DELETE |
| `admin/inventory/movements/` | GET | — |
| `admin/inventory/products/{id}/adjust/` | POST | — |
| `admin/orders/` | GET | — |
| `admin/orders/{id}/` | GET | — |
| `admin/orders/{id}/status/` | PATCH | — |
| `admin/payments/` | GET | — |
| `admin/payments/{id}/` | GET | — |
| `admin/payments/{id}/refunds/` | — | POST |
| `admin/payments/{id}/refunds/{refund_id}/simulate/` | — | PATCH |
| `admin/payments/providers/` | GET | — |
| `admin/payments/reconciliation/` | GET | — |
| `admin/payments/transactions/` | GET | — |
| `admin/product-history/` | GET | — |
| `admin/product-history/{id}/` | — | GET |
| `admin/product-images/` | GET, POST | — |
| `admin/product-images/{id}/` | PATCH, DELETE | GET |
| `admin/products/` | GET, POST | — |
| `admin/products/{id}/` | GET, PATCH | DELETE |
| `admin/products/{id}/views/` | GET | — |
| `admin/ranking-weights/` | GET | — |
| `admin/ranking-weights/{id}/` | PATCH | GET |
| `admin/recommendation-settings/` | GET, PATCH | — |
| `admin/reports/most-viewed-products/` | GET | — |
| `admin/reports/popular-categories/` | GET | — |
| `admin/reports/popular-products/` | GET | — |
| `admin/reviews/` | GET | — |
| `admin/reviews/{id}/` | PATCH | GET |
| `admin/reviews/{review_id}/replies/` | POST | — |
| `admin/seo/` | GET, POST | — |
| `admin/seo/{id}/` | PATCH | GET, DELETE |
| `admin/users/` | GET | — |
| `admin/users/{id}/` | PATCH | GET |
| `auth/login/` | POST | — |
| `auth/logout/` | POST | — |
| `auth/me/` | GET, PATCH | — |
| `auth/password/change/` | POST | — |
| `auth/password/recovery/` | POST | — |
| `auth/password/recovery/confirm/` | POST | — |
| `auth/password/recovery/email/` | POST | — |
| `auth/password/recovery/email/confirm/` | POST | — |
| `auth/register/` | POST | — |
| `auth/token/refresh/` | POST | — |
| `cart/` | GET | — |
| `cart/items/` | POST | — |
| `cart/items/{id}/` | PATCH, DELETE | — |
| `categories/` | GET | — |
| `categories/{slug}/` | GET | — |
| `categories/{slug}/children/` | GET | — |
| `categories/suggested/` | GET | — |
| `dashboard/favorites/` | — | GET |
| `dashboard/notifications/` | GET | — |
| `dashboard/overview/` | GET | — |
| `dashboard/reviews/` | GET | — |
| `dashboard/searches/` | GET | — |
| `dashboard/views/` | GET | — |
| `favorites/` | GET | — |
| `favorites/{product_id}/` | POST, DELETE | — |
| `favorites/status/` | GET | — |
| `orders/` | GET, POST | — |
| `orders/{id}/` | GET | — |
| `orders/{id}/cancel/` | POST | — |
| `payments/` | GET | — |
| `payments/{id}/` | — | GET |
| `payments/{id}/status/` | GET | — |
| `payments/callback/{provider}/` | — | POST |
| `payments/initiate/` | POST | — |
| `payments/mock/{id}/simulate/` | POST | GET |
| `products/` | GET | — |
| `products/{product_id}/reviews/` | GET, POST | — |
| `products/{slug}/` | GET | — |
| `products/{slug}/related/` | GET | — |
| `products/{slug}/similar/` | GET | — |
| `products/best-discounts/` | GET | — |
| `products/best-selling/` | GET | — |
| `products/most-favorited/` | — | GET |
| `products/most-viewed/` | GET | — |
| `products/popular/` | GET | — |
| `products/recommended/` | GET | — |
| `recommendations/from-favorites/` | GET | — |
| `reviews/{id}/` | PATCH, DELETE | — |
| `search/popular/` | GET | — |
| `search/products/` | GET | — |
| `search/recent/` | — | GET |
| `search/suggestions/` | GET | — |
| `store/contact/` | POST | — |
| `store/newsletter/` | POST | — |
| `store/newsletter/confirm/` | POST | — |

## Validation and files

- Django was tested on isolated PostgreSQL 17.12 with a Redis cache. The full suite passed 129 tests, including the two new tests for favorite privacy and completed-order bestseller ranking. OpenAPI validation succeeded for 94 paths and migration checks found no model changes.
- The browser suite passed 36 tests and uses a real Django service and the same isolated database. It covers the 27 page checks at seven viewport sizes plus login and refresh/logout, Persian search and suggestions, favorites, checkout with server totals and Mock payment, order status changes, profile and inventory updates, denial of unauthorized admin access, administrative catalog/SEO, registration/address/review moderation, and the contact form. Isolated settings use higher throttles for the browser run.
- Backend file changes are `config/urls.py`, `favorites/api.py`, `products/api.py`, and `core/test_integration_catalog.py`. The frontend keeps its server-side API structure. Major changes are in `src/lib/catalog.ts`, `src/lib/session.ts`, `src/app/actions.ts`, and the storefront, catalog, account, checkout and admin components; `frontend/tests/storefront.test.mjs` adds session and cart coverage.
- No migration or public deployment was part of this integration change.

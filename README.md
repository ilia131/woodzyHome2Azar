# HomeAksoria Backend

## Phase 0 checkpoint

This checkpoint contains mobile authentication, the multi-product catalog,
hierarchical categories, per-product SEO, favorites, product-view analytics,
Persian/English catalog search, product and category recommendations, moderated product reviews, and the authenticated user dashboard.
The catalog uses PostgreSQL and Redis. See Swagger at `/api/docs/`, OpenAPI
at `/api/schema/`, and ReDoc at `/api/redoc/`.

Phase 0 includes local Docker deployment. Phase 1 currently includes delivery addresses,
cart, unpaid order creation, inventory reservations, cancellation and historical order retrieval.
Payment gateways follow in later work.

## Run with Docker

Run `./start` from the project directory. Docker Compose and OpenSSL are
required. The launcher generates distinct credentials, provisions database
roles, and runs the explicit migration job before starting runtime services.
The gateway listens on `http://127.0.0.1:8000` by default.

See [the PostgreSQL deployment runbook](deploy/POSTGRESQL.md) for existing
volumes, migrations, verification, and isolated tests.

The Compose profile targets localhost HTTP. For production, set a real SITE_URL,
host and CORS allowlists, TLS at the trusted edge, secure cookies, and the Django
HTTPS/HSTS settings appropriate to that proxy. Keep the generated secret stable
across restarts. Compose configures separate non-superuser runtime and migration roles. The Docker build accepts an optional BuildKit
secret named `pip_ca` for an enterprise certificate bundle.

## Run locally

Python 3.12+, PostgreSQL and Redis are required. Create a PostgreSQL database and
a role that owns it. Give that role the ability to create a test database when
running the test suite locally. Set the environment variables for your services.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DJANGO_DEBUG=1 SECURE_COOKIES=0
export POSTGRES_DB=aksoria POSTGRES_USER=aksoria POSTGRES_HOST=localhost
export REDIS_URL=redis://localhost:6379/0 SITE_URL=http://localhost:3000
# Export POSTGRES_PASSWORD using your local database credentials.
python manage.py migrate
python manage.py provision_roles
python manage.py createsuperuser
python manage.py runserver
```

Django admin is available at `/django-admin/`. Grant staff model permissions
directly or via Django Groups for API access. The product metrics endpoint
requires `core.view_store_metrics`. Catalog write operations in the admin API
record the actor, action, model, and object ID.

Use a dedicated Redis database for tests because fixtures clear the cache.

```sh
REDIS_URL=redis://localhost:6379/15 python manage.py test accounts products categories seo favorites analytics core search
python manage.py makemigrations --check --dry-run
python manage.py spectacular --validate --fail-on-warn --file /tmp/aksoria-openapi.yaml
```

## Routes

Paths in the table are relative to `/api/v1/`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `products/` | Page through visible products. Filter by category subtree, stock, featured and effective price. |
| GET | `products/{slug}/` | Read product details and SEO metadata and record an eligible view. |
| GET | `products/{most-viewed,most-favorited,best-discounts}/` | Browse catalog rankings. |
| GET | `products/popular/`, `products/recommended/` | Browse weighted popular products or suggestions based on the caller’s catalog activity. |
| GET | `products/{slug}/similar/`, `products/{slug}/related/` | Browse related catalog items ordered by resemblance or by recency, respectively. |
| GET | `recommendations/from-favorites/` | Suggest additional products from the authenticated caller’s favorite categories. |
| GET | `categories/suggested/` | Browse category suggestions based on catalog activity and any personal affinities. |
| GET | `categories/`, `categories/{slug}/`, `categories/{slug}/children/` | Browse visible categories and direct children. |
| GET | `search/products/?q=میز` | Search visible products across titles, descriptions and category names. Supports catalog filters and pagination. |
| GET | `search/suggestions/?q=می` | Return bounded product and category suggestions. Set `limit` from 1 to 20 per group. |
| GET | `search/popular/` | Page through frequently submitted catalog phrases. |
| GET | `search/recent/` | Page through the authenticated caller's private search history. |
| GET, POST | `products/{product_id}/reviews/` | Read approved reviews or submit a review as an authenticated user. |
| PATCH, DELETE | `reviews/{id}/` | Edit or delete a review owned by the caller. |
| GET | `admin/reviews/` | List and filter reviews for authorized staff. |
| GET, PATCH | `admin/reviews/{id}/` | Read, approve or reject a review. |
| POST | `admin/reviews/{review_id}/replies/` | Post a staff reply. |
| GET | `dashboard/overview/` | Read the caller’s profile, favorite count, review summary and notification counts. |
| GET | `dashboard/{favorites,reviews,searches,views,notifications}/` | Read the caller’s private, paginated dashboard lists. |
| GET | `favorites/` | List the current account's favorite products. |
| POST, DELETE | `favorites/{product_id}/` | Add or remove the current account's favorite. |
| GET, POST, PATCH | `admin/products/` and its detail route | Manage products. Deactivate a product to retain its URL and history. |
| GET, POST, PATCH, DELETE | `admin/{categories,product-images,seo}/` and detail routes | Manage categories, individual gallery images and SEO records. |
| GET | `admin/product-history/?product={id}` | Page through stock and price snapshots. |
| GET | `admin/products/{id}/views/` | Read total, unique, guest and authenticated view counts and rolling 1-, 7- and 30-day totals. |

Use `page` and `page_size` on list endpoints. Product sorting uses
`ordering=price`, `newest`, `discount`, `favorites`, `views` or `score`, with a
leading minus sign for descending order. Catalog uploads use multipart form data.
Create one gallery record per image and use `position` to control display order.

## Data and integration

- A category can have multiple child categories and products. PostgreSQL walks
  the public category tree in the query. Reparenting is serialized to prevent
  cycles. Product slugs support Persian, are globally unique, and are immutable
  after creation.
- Product writes via `save()` record the initial price and stock and any
  changes in the same transaction. Use this path for catalog mutations. Bulk SQL
  operations bypass that history. The admin API locks the product before applying
  a partial update, and the database enforces price and discount constraints.
- The image validator accepts JPEG, PNG or WebP up to 5 MiB and 20 megapixels.
  New files use UUID names under separate directory prefixes. Persist the default
  media directory or configure a Django storage backend and a media URL in
  production. Django serves these files directly in local debug mode.
- Next.js can build page metadata from `seo` on the product detail response.
  Offers use the effective price and `STORE_CURRENCY` (default `IRR`).
  The canonical URL defaults to `SITE_URL/products/{slug}/`. Serve or proxy
  `/sitemap.xml` and `/robots.txt` from the public site at `SITE_URL`.
  Inactive products and those under inactive categories return 404. Out-of-stock
  products remain public with Schema.org `OutOfStock`. Products marked
  `noindex` or canonicalized to another URL are omitted from the sitemap.
- Redis deduplicates views per visitor and product for 30 minutes. Analytics
  persists keyed pseudonyms without storing raw IP addresses, phone numbers, or
  user agents. Guest identities derive initially from a coarse fingerprint and
  persist via a signed cookie. Guest uniques are approximate, especially when
  multiple visitors share a network and user agent.
- Password changes blacklist all outstanding refresh tokens, and tokens with
  a previous password signature are rejected. Account recovery delivery and
  phone ownership verification have interfaces for future integration.


## Search integration

- Send `q` with 2–120 characters after normalization. Arabic and Persian
  variants of yeh/kaf, half-spaces, repeated spaces, diacritics, and letter case
  are normalized. The response keeps original product and category labels.
- Use `search/suggestions/` while typing with a client-side debounce, and
  `search/products/` for submitted searches. The latter accepts the catalog
  filters `category`, `in_stock`, `featured`, `min_price`, `max_price` and
  `ordering`. The default ordering ranks exact title and prefix matches ahead
  of other matches.
- Only page 1 of submitted product searches writes history. Signed-in users
  can revisit their normalized queries, including searches without results.
  A repeated phrase updates its existing history entry. The public popular
  list counts searches with results whose phrase appears in a visible catalog
  title or category name, and checks current visibility when serving the list.
- Migration `search.0002_search_indexes` enables `pg_trgm` and creates five
  PostgreSQL GIN indexes. The migration role needs permission to create the
  extension if the database administrator has not installed it. PostgreSQL
  uses the `simple` text configuration for normalized Persian and English
  tokens. Fuzzy matching uses trigrams on product titles and category names.


## Recommendations

Recommendations share the public catalog visibility rules. Out-of-stock
items remain eligible. Similar and related products use the immediate category
family and PostgreSQL trigram similarity on normalized product titles and
descriptions. Product feeds exclude the source product.

Personalization uses recent favorites and up to 20 distinct visible viewed
products from the previous 30 days. At least two distinct viewed products
are required before account views contribute. The recommendations feed
excludes favorited products and the recent view seeds that contributed.
Guests and users without enough signals receive the popularity ordering.
The favorites-only feed requires authentication and may return an empty list.
Suggested categories have at least one visible product directly assigned to
them. Personalized responses use private, no-store cache headers.

Override recommendation weights, the history window, or the view threshold
in Django's `RECOMMENDATION_OPTIONS` setting. Popularity ordering independently
uses the `views` and `favorites` values in the existing `RankingWeights` model.
Migration `analytics.0002_productview_analytics_account_views_idx` indexes
authenticated pseudonymous view history. No external service is required.


## Reviews

Each account can have one review per product. A duplicate submission returns
HTTP 409. Reviews are pending when submitted and after an actual change by the
author. Authors can delete their own review and submit a new one afterwards.
Public reviews can be filtered by `rating` and ordered by `created_at` or
`rating` (prefix with `-` for descending order). The product response reports
the count and average rating from approved reviews only.

Staff require `reviews.view_review` to read management endpoints,
`reviews.change_review` to approve or reject, and
`reviews.add_reviewreply` to reply. Send an explicit `is_approved` boolean
when moderating. A non-approved review with a `moderated_at` timestamp has
been rejected. Staff moderation decisions and replies appear in the audit log.
Public responses omit author account identifiers and show replies only under
approved reviews. The reply model supports a nullable parent reference. The
current write API creates top-level staff replies.


## User dashboard

All dashboard endpoints require authentication and return private, no-store
responses. Overview includes every saved favorite in the total. The favorites
list follows public catalog visibility. The review summary uses the caller’s
reviews across all moderation states and returns a null average for no reviews.
The reviews list includes moderation status and timestamps.

Search history reuses saved account searches. Product view history shows
recorded account events for currently visible products, newest first. Guest
activity is excluded. The notifications list exposes the stored read timestamp
and derived read state. Reading the list leaves the stored state unchanged.
The dashboard currently covers the Phase 0 feeds. Order history and addresses have dedicated endpoints.

Migration `notifications.0002_notification_notifications_user_latest_idx`
indexes notification lookup and ordering by account.


## Admin API and roles

- `/api/v1/admin/users/` lists and searches customer accounts. Patch a
  customer detail with an explicit `is_active` decision. Existing access and
  refresh tokens remain revoked on reactivation.
- `/api/v1/admin/ranking-weights/` exposes defaults and updates for catalog
  and popularity ranking. `/api/v1/admin/recommendation-settings/` supplies
  sparse overrides for similarity weights and personalization limits.
- `/api/v1/admin/reports/{popular-products,most-viewed-products,popular-categories}/`
  provides paginated reports. Product-level view metrics remain available at
  `/api/v1/admin/products/{id}/views/`.
- `/api/v1/admin/audit-logs/` lists recorded administrative changes for
  authorized administrators.

Run `python manage.py provision_roles` to apply the Phase 0 grants for the
managed groups. Membership and the staff flag must be granted by a trusted
administrator. Admin manages the Phase 0 resources. Product Manager has
catalog and metrics access. Support Manager can read customer details and
moderate reviews. Super Admin authority comes from the Django superuser flag.
The Order Manager group has read access to orders and inventory movements. Re-running provisioning restores
the defined permissions on these managed groups.

## Phase 1 addresses and cart

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/api/v1/addresses/` | List or create delivery addresses. |
| GET, PATCH, DELETE | `/api/v1/addresses/{id}/` | Read, edit, or delete your own address. |
| GET | `/api/v1/cart/` | List the cart with live prices, availability, and a subtotal for available lines across all pages. |
| POST | `/api/v1/cart/items/` | Add a product or set the existing line to an absolute quantity. |
| PATCH, DELETE | `/api/v1/cart/items/{id}/` | Change quantity or remove a line. |

All endpoints use JWT and return private, no-store responses. The first
address becomes default. Selecting another default replaces it, and deleting
the default promotes the oldest remaining address. Iranian postal codes are
stored as ten ASCII digits. Recipient phone numbers reuse account normalization.

The cart stores quantities only and calculates prices from the current catalog.
Unavailable lines stay removable and are excluded from the subtotal. Quantity
updates return HTTP 409 when stock is insufficient. Cart mutations do not reserve
or deduct inventory. Checkout reloads prices and product data under the account lock.
Address and cart mutations record audit metadata without copying address contents into the audit log.

## Phase 1 step 2 order creation and snapshots

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/orders/` | Create an unpaid order from the whole cart. The only request field is the owner's `address_id`. |
| GET | `/api/v1/orders/` | List the caller's orders, newest first, with the standard pagination envelope. |
| GET | `/api/v1/orders/{id}/` | Read a single order owned by the caller. |

A syntactically valid address ID that is missing or belongs to another
account returns HTTP 404. Empty carts, hidden products and quantities above
current stock return HTTP 409. Unexpected input fields return HTTP 400.
Prices use the current discounted catalog price where one exists. Shipping
and additional order-level discount are zero at this step.

Checkout takes the same account row lock as cart and address writes. It reads
catalog prices, stock and visibility for the entire cart in one SQL statement.
Order creation, item insertion, creation audit and deletion of the consumed
lines commit in the same transaction. A failed write leaves the cart intact.
Two concurrent requests cannot turn the same cart into two orders. Orders
start in `pending_payment`.

The order stores the delivery address snapshot. Items store title, slug,
SKU, image storage key, quantity and amounts as they were at purchase.
The response uses stored values. Product or address deletion nulls the
corresponding reference and retains the snapshot. Deleting a physical image
file can invalidate the stored key. Account deletion is protected while
orders reference it. The audit metadata contains only order number and item count.

## Phase 1 step 3 inventory and unpaid order lifecycle

`Product.stock` is the sellable quantity. Checkout subtracts available units
and creates one active reservation per order line. Cancellation and expiration
restore available units once. An internal consumption service changes a hold
from active to consumed without a second deduction. No route invokes consumption
or sets an order to paid, processing, or completed.

Checkout locks the account, then all needed product rows by ascending ID, and
validates stock and prices under those locks. Reservations, ledger, order,
snapshots, audit and clearing the cart commit together. Cancellation and
expiration lock the order, its active reservations, and then products in
ascending ID order. The ledger stores an operation key, quantity, available
delta and available balance, associated references and optional actor.
Historical snapshots and existing product balances survive migration. Existing
orders without reservations remain readable and are ineligible for cancellation.

The default hold is 900 seconds, configurable with
`INVENTORY_RESERVATION_SECONDS`. Celery Beat schedules expiration every 60
seconds. Checkout first reclaims expired holds for its candidate products.
Overdue cancellation finalizes expiration and returns HTTP 409; repeat
cancellation or cancellation of other ineligible states also returns 409.
Order reads reflect the persisted lifecycle, so they can still show an overdue
order as pending briefly before reconciliation. Active reservations protect
their product from deletion.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/orders/{id}/cancel/` | Cancel an owned pending order with active, unexpired holds. |
| GET | `/api/v1/admin/orders/` | Paginated orders filtered by number, user, status and ISO datetime range. |
| GET | `/api/v1/admin/orders/{id}/` | Order detail and reservation states. |
| GET | `/api/v1/admin/inventory/movements/` | Paginated ledger filtered by product snapshot ID, order or kind. |
| POST | `/api/v1/admin/inventory/products/{id}/adjust/` | Adjust available stock with a signed integer delta and UUID operation ID. |

Staff need `orders.view_order`, `orders.view_inventorymovement` or
`orders.add_inventorymovement` for the corresponding operation. An adjustment
retry with the same actor, product, UUID and delta returns the original movement.
An absolute stock edit on the product API requires current `stock_revision`.
The dedicated adjustment endpoint accepts `delta` or `target` with
`expected_revision`, plus a UUID. A stale revision returns HTTP 409.
Refresh the product before re-confirming the adjustment. Both paths use
the inventory service and require adjustment permission. Django admin displays stock read-only for existing
products. Re-run `python manage.py provision_roles` after migration if deploying
outside Compose.

## Phase 2 mock payments

The payment foundation is available for local development and test only.
Production settings disable the mock and reject enabling it. For API
usage, settings and scenario details, see
[Payment architecture](docs/PAYMENT_ARCHITECTURE.md) and
[Mock gateway testing](docs/MOCK_PAYMENT_TESTING.md).

## WoodzyHome frontend

See [frontend/README.md](frontend/README.md) for local setup and connection to the existing API. The [Figma mapping](docs/FIGMA_SCREEN_MAPPING.md) and [frontend report](docs/WOODZYHOME_FRONTEND_REPORT.md) document the 27 views and their verification.

## Production readiness

See [the production readiness report](docs/WOODZYHOME_PRODUCTION_READINESS.md) for the 27 views, captured layouts and deployment checks. Recovery and newsletter confirmation require a configured SMTP relay and a Celery worker. Set the SMTP variables from `.env.example` before enabling `TRANSACTIONAL_EMAIL_ENABLED`, and verify delivery with the intended sender domain in a controlled environment. Run migrations with the Migration role and provision groups with `manage.py provision_roles`. The contact inbox is available in Django Admin to staff with the contact-message view permission.

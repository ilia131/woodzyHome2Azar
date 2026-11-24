# WoodzyHome storefront

Persian RTL frontend for the existing HomeAksoria Django application. It implements eight storefront views, six customer views, four checkout views and nine administration views. A view can use a parameterized route for its detail state.

## Run locally

Requires Node.js 20.9+.

```sh
npm ci
cp .env.example .env.local
npm run dev
```

Set `DJANGO_API_URL` to the existing backend's server-reachable versioned base, for example `http://127.0.0.1:8000/api/v1`. Set `STORE_CURRENCY` to match Django. Set `LIVING_CATEGORY_SLUG` when the living-room category uses another slug. Public screens can use the separately maintained showcase catalog in development with explicit opt-in. Account, order, checkout and administration records always require Django. Deploy connected mode over HTTPS so the browser can send the secure HttpOnly server session cookie.

`npm run typecheck` runs the strict TypeScript check. `npm run build` builds the application. `npm test` expects a running app; install Playwright Chromium or set `CHROMIUM_EXECUTABLE`. Set `WOODZY_TEST_URL` to change the target. For connected tests use a disposable Django database with an active living category, a product with slug `qa-sofa`, a staff test account with full permissions and a default address, and the Mock provider enabled in test mode. Set `WOODZY_TEST_STAFF_PHONE` and `WOODZY_TEST_STAFF_PASSWORD`. Set `WOODZY_TEST_CUSTOMER_PHONE` and `WOODZY_TEST_CUSTOMER_PASSWORD` to verify ordinary customer denial. The suite mutates the disposable fixture. Use a fresh fixture for each run.

## Source layout

- `src/app` contains the Next.js routes, server actions, shared layout and same-origin autocomplete route.
- `src/components` contains the storefront shell, cards, filter layout, gallery, category directory, search and shared tables/forms for operational views.
- `src/features` defines the customer, checkout and administration views and a server-side allowlist of accepted mutations.
- `src/lib` contains the DRF adapters, shared types, protected request handling and isolated showcase catalog.
- `src/app/tokens.css` contains the provisional palette, font and visual effects. The [Figma mapping](../docs/FIGMA_SCREEN_MAPPING.md) records the geometric reference.
- `tests/storefront.test.mjs` covers page rendering, no page-level horizontal scroll at the five brief viewport sizes plus 320 and 1280 px, Persian search, favorites, checkout and permission checks.

Private requests use the access token server-side with caching disabled. The backend rechecks authorization and validation for each operation. An expired access token can be renewed from the sign-in screen while its refresh token remains valid. Payment status is read from the backend; the test scenario control calls the existing mock endpoint. No real gateway was enabled.

## Assets and current limits

The hero is generated editorial photography. Supporting editorial and showcase images come from Unsplash. Product and category imagery in connected mode comes from Django. The wordmark is provisional. Place the official logo under `public/` and set `WOODZY_LOGO_PATH` to its public path to use it in the header and footer. Figma styles and renders remain unavailable through the connection. Contact submissions are stored by Django. Public showroom details need supplied content. Password recovery and newsletter confirmation require the configured Django transactional email service. See the [screen-by-screen report](../docs/WOODZYHOME_FRONTEND_REPORT.md) for verification status.

### Connected execution

Set `DJANGO_API_URL` in `.env.local` to the Django API base reachable **from Next.js**. For example, use `http://127.0.0.1:8000/api/v1` when both run directly on the same machine. If Django serializes a private network media host, set `DJANGO_MEDIA_URL` to the browser-facing media base. Both must be deployment configuration. Restart Next.js after changing them.

A missing API base produces a connection error. Set `WOODZY_SHOWCASE=1` explicitly to use the showcase catalog under `next dev`. Production builds never use that catalog. Allow the mock payment UI only for an isolated backend configured with `PAYMENT_MODE=test` by setting `WOODZY_TEST_PAYMENTS=1`; keep it disabled on the public storefront.

The BFF keeps the access token and rotating refresh token in HttpOnly cookies. Use **تمدید نشست** on the sign-in screen after an access token expires. Logout revokes the backend refresh token before clearing the cookies. Use HTTPS in production so secure cookies can be sent.

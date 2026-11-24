# Phase 2 provider readiness report

## Current implementation

The existing Payment Core remains responsible for initiation, verification,
callback replay controls, refunds, reconciliation, order state and reservation
settlement. Mock is the only adapter with working payment behavior and is
available only in development/testing when enabled. No real financial requests
were sent and no real provider was activated.

| Provider | Adapter | Configured | Effective enabled | Ready for real transactions | Status |
| --- | --- | --- | --- | --- | --- |
| Mock | MockPaymentProvider | Local implementation | Development/test only, subject to setting | No | test_ready or disabled |
| Snapp Pay | SnappPayProvider | No | No | No | pending_credentials |
| DigiPay | DigiPayProvider | No | No | No | pending_credentials |
| Torob Pay | TorobPayProvider | No | No | No | pending_credentials |

All three provider-specific adapters implement the baseline contract by
failing closed. Initiation and each named callback return HTTP 503 with
PROVIDER_NOT_CONFIGURED before any payment or inventory mutation. There is
no fallback to Mock or generic external signature scheme. Staff with payment
read permission can inspect GET /api/v1/admin/payments/providers/. The
response distinguishes requested enablement from effective enablement and
does not include secrets. There is no administrative activation method.

## Verification

- Ran **121 tests in 20.839s**, result **OK**, using PostgreSQL 17.12 and Redis
  7.4.12 with isolated test state. Existing PostgreSQL concurrency, inventory
  and Mock regressions passed, along with five added registry/security tests.
- Django system check passed with all three external enable flags present and
  no credentials. Explicit production activation of Mock still fails startup.
- Migration check passed with the Migration role. Model-drift check reported
  **No changes detected**. This extension adds no migrations and does not
  change role separation or recreate the database.
- OpenAPI validated with warnings treated as errors and documents the status
  endpoint, structured 503 responses, and that the shown callback contract is
  for Mock only.
- Compose configuration parsed successfully. No full-stack image rebuild or
  fresh Compose deployment was performed. The earlier environment storage
  limitation remains relevant.

## Missing integration evidence

For each provider, obtain independently verified official documentation,
merchant onboarding and sandbox credentials. Confirm authentication,
currency units, initiation, callback authenticity and retry semantics,
server-side verification, refunds and settlement reconciliation. Complete
sandbox and provider acceptance tests, production secret provisioning, and
security and operational review before any live activation. See
docs/PROVIDER_INTEGRATION_CHECKLIST.md for the detailed requirements.

## Git integration

The requested remote contained no branches when inspected. An isolated release
checkout imports an allowlisted source baseline and then layers the provider
changes on feat/phase2-credit-providers. Local environment files, databases,
backups, operational audit artifacts and caches are omitted. No default/base
branch changes are part of this release. Phase 3 has not been started.

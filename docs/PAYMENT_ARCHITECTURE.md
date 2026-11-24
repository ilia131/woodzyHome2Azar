# HomeAksoria payment architecture

Phase 2 implements a mock-only gateway. Django settings reject
`PAYMENT_MODE=production` with Mock enabled. No provider can process real payments.
Compose defaults to production with Mock disabled. No real capture or refund
exists in this implementation.

## Data and services

- Payment binds the account and order, copies amount and currency from the
  order, and stores the attempt UUID, provider reference, URL, expiration and
  state. The account/idempotency key binds retries to one operation. Conditional
  uniqueness prevents multiple active attempts and multiple accepted settlements
  per order.
- PaymentTransaction records initiation, verification, captures, reconciliation
  and simulated refund events. The app exposes read-only history. A capture
  reference is unique per provider. The log stores allowlisted metadata and
  never stores client card data or callback bodies.
- PaymentWebhookEvent deduplicates authenticated callback events by provider and
  event ID. Processing results and sanitized error codes are stored.
- MockSession represents provider-side state separately from Payment.
- Refund tracks the requested amount, requester, UUID, state and provider
  reference. Full or partial amounts are checked against verified captured funds
  and prior allocated refund requests.

## Initiation and verification

Initiation locks Account → Order → Reservations, checks ownership, order/hold
eligibility and positive total, creates the attempt and commits. The adapter is
invoked outside those locks. A second atomic operation records the result.
A definite provider rejection yields failed. Ambiguous outcomes stay processing
and reuse the same merchant UUID. A response lost after the first database
commit is recoverable through reconciliation.

A callback must authenticate before provider lookup. Mock checks a time-bound
HMAC with constant-time comparison. Then a separate verification read retrieves
provider state, authority, merchant UUID, amount, currency and capture reference.
The callback body never supplies a trusted outcome or amount. There is no
user-accessible verification endpoint. The signed provider callback uses neither
browser session cookies nor CSRF authentication. Authenticated application
endpoints use JWT. Both entry points are throttled.

Results apply in one transaction with Order → Payment → Reservations → Products
in ascending product ID. If the active hold is eligible, consumption leaves
sellable stock unchanged and records one terminal inventory movement. For a
success after expiry, the inventory service checks the complete order under
product locks, releases due holds if present, creates fresh holds and consumes
them together. Old reservation records remain intact. Missing available stock,
partial eligibility, or a cancelled order sends the payment to review and
never marks the order paid. A cancelled order stays cancelled. An unpaid or
expired order that needs manual attention can enter payment_review.

## State transitions

Created attempts become pending, processing or failed at initiation; they can
also expire. A verified result can move active attempts to succeeded, failed,
cancelled, expired or review. Verified late success can recover failed,
cancelled or expired *payment attempts*, subject to order and inventory rules.
Terminal settled payment states cannot become failed on replay. Every material
transition is audited. A verified settlement and order-paid update share the
inventory transaction.

Staff request refunds via a permission-controlled operation. A separate
development-only action records a simulated provider reference and transaction.
It does not report a completed bank refund, move inventory, or trigger another
gateway. Parent payment remains refund_pending or requires_review. Refunded and
partially_refunded are reserved for independently verified future refunds.

## Reconciliation and provider contract

Beat invokes reconciliation every 60 seconds, examining at most 100 candidates
per run, rotated by last update. It can recover uncertain initiation, check
provider outcomes, and time out overdue attempts. Verification failures,
duplicate capture references, unavailable stock and late results are surfaced in
history or the admin reconciliation view. The admin view also exposes
order/payment mismatches. A failed lookup never authorizes success.

Implement a provider using BasePaymentProvider and normalized initiation and
verification results. The adapter must authenticate callbacks, normalize its
event identity, verify via the provider's official server interface, map
currency units and states, set network timeouts, and support retries/recovery
using the merchant UUID. Register it only after acquiring verified
documentation, production credentials via a secret manager, callback origin and
signature rules, settlement/refund contracts, compliance approval, and
test/sandbox acceptance. Providers must return stable capture IDs and safe
payment URLs. Refund completion requires a verified provider result and a
separate settlement policy. No real-provider endpoints are assumed here.

## Environment

`PAYMENT_MODE` selects production, development or test. Mock defaults on only
in development/test when the enable flag is omitted. Compose explicitly
defaults `PAYMENT_MOCK_ENABLED` to false. `PAYMENT_MOCK_SIGNING_KEY` can contain a
separate local secret. With no dedicated key the Mock uses Django's secret
under a dedicated signing scope. `PAYMENT_DEFAULT_PROVIDER` is mock.
`PAYMENT_PENDING_EXPIRATION_SECONDS` caps the attempt lifetime, which is also
bounded by the original hold. `PAYMENT_INITIATION_TIMEOUT` and
`PAYMENT_VERIFICATION_TIMEOUT` are reserved adapter budgets; the local mock
simulates uncertainty without blocking I/O. Deploy migrations with the
existing Migration role and reprovision staff permissions.

A local attempt deadline does not prove the provider closed the attempt.
A locally expired but unresolved attempt blocks a new attempt while
reconciliation checks it. Provider-confirmed failure, cancellation, or expiry
allows a new attempt if the order and reservation are still eligible.

## Pending providers

The registry recognizes Mock, Snapp Pay (`snapp_pay`), DigiPay (`digipay`) and
Torob Pay (`torob_pay`). The last three have separate fail-closed adapters.
Each can implement its own official protocol later. Initiation and the named
callback URLs now return HTTP 503 with `PROVIDER_NOT_CONFIGURED` before a payment
attempt is created or a callback is parsed. No provider falls back to Mock.
The existing settlement and inventory locks are shared integration points.

Staff with payment read permission can inspect
`GET /api/v1/admin/payments/providers/`. The response distinguishes
registration, verified configuration, requested vs effective enablement,
and readiness for real transactions. A requested enable flag does not activate
any pending adapter. Configuration is environment-managed, so this API has no
write or activation action to audit. Follow the deployment change log when
editing provider flags. Audit existing payment and refund events through the
normal application APIs.

The provider flags and empty credential placeholders in `.env.example` do not
describe official protocols. Placeholder credentials are not consumed by the
adapters. See [the provider integration checklist](PROVIDER_INTEGRATION_CHECKLIST.md)
for the verification and activation gates.

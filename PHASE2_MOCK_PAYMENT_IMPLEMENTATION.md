# HomeAksoria Phase 2 mock payment implementation

## Delivery and scope

The payment foundation is implemented with Mock as the only provider.
Production settings disable Mock by default and reject explicit production
enablement. No external financial request was sent. Phase 3 was not started.

## Architecture, data and APIs

Payment creation and settlement live in `payments/services.py`. The user
selector scopes records to the current buyer. `payments/providers/base.py`
defines normalized initiation and verified results and an interface for
initiation, signed callback processing, server verification, status polling
and optional refunds. `MockPaymentProvider` uses a separate persistent provider
session and generates a same-origin simulation URL. DRF serializers frame
request/response data, and Django model permissions protect staff operations.

- Payment records order-priced attempts, idempotency and deadline.
- PaymentTransaction is append-only through the application services and tracks
  initiation, capture, verification, reconciliation and refund simulation.
- PaymentWebhookEvent records verified-identity callback processing, deduplicated
  by provider and normalized UUID.
- MockSession stores simulated external provider state. Refund tracks a
  requested full/partial amount, operator, UUID and mock reference.
- Migration `orders.0005_alter_order_status_alter_reservation_item_and_more`
  permits historical replacement holds while ensuring only one active hold
  per item, and adds order payment_review. Migration `payments.0001_initial`
  creates the payment tables and constraints. Both applied through
  `aksoria_migration` to the isolated existing Phase 1 PostgreSQL database
  `aksoria_remediation_fresh`. No historical migration was edited and the
  main application database was not upgraded during this verification.

| Methods | Route |
| --- | --- |
| POST | `/api/v1/payments/initiate/` |
| GET | `/api/v1/payments/`, `/api/v1/payments/{id}/`, `/api/v1/payments/{id}/status/` |
| POST | `/api/v1/payments/callback/{provider}/` |
| GET, POST | `/api/v1/payments/mock/{id}/simulate/` |
| GET | `/api/v1/admin/payments/`, `/api/v1/admin/payments/{id}/`, `/api/v1/admin/payments/transactions/`, `/api/v1/admin/payments/reconciliation/` |
| POST | `/api/v1/admin/payments/{id}/refunds/` |
| PATCH | `/api/v1/admin/payments/{id}/refunds/{refund_id}/simulate/` |

Initiation reads amount and currency exclusively from the locked order.
Unknown input fields, including any client-provided amount, do not affect
pricing. One active attempt per order and one accepted successful settlement
are DB constraints. The same buyer UUID replays the original attempt. Locally
expired but unconfirmed attempts cannot be replaced until the gateway confirms
a terminal outcome. Transaction outcome transitions are service-only and
audited. Admin payment views filter provider/state/date and search order
number/reference. There is no staff action that marks a payment successful.

## Verification and inventory

The mock gateway simulates success, failure, cancellation, timeout, invalid
signature, invalid amount/reference, unavailable verification, delayed results
and replay. The callback validates scoped timestamped HMAC and authorizes
changes only from separately verified mock provider state. A redirect or
a caller-supplied outcome is insufficient. Callback and reconciliation use
the same locked settlement path. No provider call runs inside inventory locks.

Live holds are consumed once with zero additional stock deduction. Expired
orders can be allocated anew only if the entire cart is still sellable under
ordered product locks; old holds remain historical. Cancelled orders are
not reopened. Verified receipts that cannot be allocated go to review.
A duplicate provider capture reference and incompatible order/payment states
are identifiable through review and reconciliation, with no new stock mutation.
Refunds are bounded by the confirmed captured amount; the Mock simulation
records a clearly labeled provider reference and never reports a bank refund
or automatically changes stock.

Reconciliation is capped at 100 candidates per run. A Beat schedule runs every
60 seconds; provider reads are outside locks. The task recovers uncertain
initiation by merchant identity, checks overdue attempts, and routes verified
results through the settlement service. Admin reconciliation lists review,
overdue and state-mismatch records.

## Verification and boundaries

- Django system checks, migration drift check and OpenAPI with
  `--validate --fail-on-warn` succeeded. Twelve payment paths are present.
- Final run: `Ran 116 tests in 21.764s` and `OK`. This includes all 98 prior tests and 18 payment tests.
- PostgreSQL **17.12** and Redis **7.4.12** were used. The test suite covers
  account isolation, provider outcomes, callback security and idempotency,
  refund simulation, legacy regressions, and PostgreSQL races against
  duplicate callbacks, expiry, cancellation and stock adjustment.
- Explicit production enablement returned
  `ValueError: The mock gateway cannot run in production.`
- A separate temporary Celery worker with Runtime credentials and an isolated
  Redis broker responded to ping and successfully processed
  `payments.tasks.reconcile_payments`. Task tests cover actual mock state
  recovery. The worker smoke used an empty isolated database and did not
  independently exercise Beat timing.
- Compose configuration validation succeeded. PostgreSQL, Redis and the
  existing Web container were healthy, but the audit environment did not
  rebuild or start all Phase 2 services. No full-stack Compose verification
  or production readiness claim is made. The persistent project database
  and its volumes were kept intact.

## Remaining real-provider requirements

Obtain official bank sandbox/API documentation, currency/unit and error
mapping, merchant identifiers, credential provisioning/rotation, verified
success and refund contracts, reliable callback signature and replay rules,
and reconciliation/settlement reports. A new adapter must supply safe URLs,
stable provider references, recovery keyed by the merchant UUID and enforce
network timeout budgets. Add role-controlled real review/refund completion
only after verified provider support, and test late captures, split refunds,
duplicate callbacks and operational monitoring with the provider. See
`docs/PAYMENT_ARCHITECTURE.md` and `docs/MOCK_PAYMENT_TESTING.md`.

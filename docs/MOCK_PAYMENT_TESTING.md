# Testing the mock payment gateway

Use a disposable development or test database. Set PAYMENT_MODE=development
and PAYMENT_MOCK_ENABLED=true for the development web and Celery processes.
Compose defaults to disabled. Run migrations and provision roles first.
Authenticate, add an in-stock product to a cart, save an address, and create an
order. Submit the order ID and a fresh UUID to POST /api/v1/payments/initiate/.
The returned URL is a relative same-origin JSON simulation endpoint. Use the
same JWT as the buyer; no browser-only redirect confirms payment.

POST a JSON body containing scenario to the returned URL. Use distinct checkout
orders or retryable attempts where necessary. Consult the status endpoint
GET /api/v1/payments/{id}/status/.

| Scenario | Effect |
| --- | --- |
| success | A signed callback is verified against the mock store, then settlement consumes the eligible hold. |
| failure | Provider reports failure and the attempt can be retried on a new key while the hold remains valid. |
| cancel | Provider cancels the payment attempt. Cancelling the actual order has its own endpoint. |
| timeout | Provider reports an expired attempt. |
| invalid_signature | Callback is rejected with HTTP 403; mock financial state remains unchanged. |
| invalid_amount | Verification reports a different amount and sends the payment to review. |
| invalid_reference | Verification reports a different authority and sends the payment to review. |
| invalid_verification | Mock verification is unavailable, leaving processing/retry evidence. Use a separate attempt for later success. |
| delayed | The attempt remains processing; submit success later to simulate eventual completion. |
| duplicate callback | Repeat success on the same payment. The saved terminal outcome and capture count stay unchanged. |

For late-success scenarios in fixtures, expire the hold after initiation. Leave
available stock for reacquisition, or reserve it from another order to verify
manual review. Do not modify real orders. Staff with refund permissions may
request a full or partial amount, then simulate a refund. The resulting
reference starts with mock-refund- and the request state is simulated.
This operation never moves inventory and never reports a completed bank refund.

Run PostgreSQL integration tests with `python manage.py test payments` using a
disposable PostgreSQL test database and isolated Redis logical database.

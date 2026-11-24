# Provider integration checklist

Snapp Pay, DigiPay and Torob Pay are all pending credentials and official
documentation. Confirm the exact requirements independently for each provider.
Environment names are placeholders, and no shared protocol is assumed.

| Required evidence | Snapp Pay | DigiPay | Torob Pay |
| --- | --- | --- | --- |
| Official API documentation and version | Obtain | Obtain | Obtain |
| Merchant onboarding, permitted products, eligibility and settlement terms | Confirm | Confirm | Confirm |
| Approved sandbox credentials and test merchant | Obtain | Obtain | Obtain |
| Production credentials, rotation and secure storage | Obtain after approval | Obtain after approval | Obtain after approval |
| Authentication and token lifetime | Confirm | Confirm | Confirm |
| Initiation fields, currency units, reference and safe redirect | Confirm | Confirm | Confirm |
| Callback transport, signature and replay requirements | Confirm | Confirm | Confirm |
| Server verification, amount/currency/reference matching | Confirm | Confirm | Confirm |
| Refund availability, limits, verification and status | Confirm | Confirm | Confirm |
| Error/status codes and final vs uncertain outcomes | Confirm | Confirm | Confirm |
| Timeout, retries, request keys and reconciliation reports | Confirm | Confirm | Confirm |
| Sandbox scenario coverage including late/duplicate callbacks and refunds | Validate | Validate | Validate |
| Provider acceptance, compliance and production activation | Approve | Approve | Approve |

For each adapter, implement the official protocol behind BasePaymentProvider and
map provider outcomes to existing normalized results. Route verified outcomes
through Payment Core without changing inventory directly. Before exposing
callbacks, verify that unsolicited success claims cannot finalize orders.
Require sandbox acceptance, a reviewed production configuration, operational
monitoring, and a controlled rollout before marking a provider production-ready.
A flag, a secret or a populated URL alone cannot activate the current stubs.

from rest_framework.exceptions import APIException

from .base import BasePaymentProvider, InitiationResult, VerifiedResult


class ProviderNotConfigured(APIException):
    status_code = 503
    default_code = 'PROVIDER_NOT_CONFIGURED'

    def __init__(self, provider):
        super().__init__({
            'code': self.default_code,
            'provider': provider,
            'detail': 'This payment provider is not configured.',
        })


class PendingProvider(BasePaymentProvider):
    """A fail-closed contract while provider-specific protocols are unavailable."""

    def unavailable(self):
        return ProviderNotConfigured(self.identifier)

    def initiate_payment(self, payment) -> InitiationResult:
        raise self.unavailable()

    def verify_payment(self, reference) -> VerifiedResult:
        raise self.unavailable()

    def process_callback(self, payload, signature):
        raise self.unavailable()

    def get_payment_status(self, payment) -> VerifiedResult | None:
        raise self.unavailable()

    def refund_payment(self, refund):
        raise self.unavailable()

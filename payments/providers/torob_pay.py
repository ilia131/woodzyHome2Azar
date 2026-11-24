from .pending import PendingProvider


class TorobPayProvider(PendingProvider):
    """Add the documented merchant, callback and refund contracts after onboarding."""

    identifier = 'torob_pay'

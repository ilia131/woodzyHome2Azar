from .pending import PendingProvider


class SnappPayProvider(PendingProvider):
    """Implement merchant authentication, checkout and callback verification from official documentation."""

    identifier = 'snapp_pay'

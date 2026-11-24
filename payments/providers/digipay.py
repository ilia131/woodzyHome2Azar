from .pending import PendingProvider


class DigiPayProvider(PendingProvider):
    """Add provider-specific eligibility, authorization and settlement mapping after protocol review."""

    identifier = 'digipay'

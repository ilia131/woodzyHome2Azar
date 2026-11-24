from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


class ProviderUnavailable(Exception):
    """The outcome is uncertain; use the same merchant identifier to recover."""


class ProviderRejected(Exception):
    """The provider definitively rejected the request."""


@dataclass(frozen=True)
class InitiationResult:
    reference: str
    url: str


@dataclass(frozen=True)
class VerifiedResult:
    reference: str
    merchant_id: UUID
    amount: Decimal
    currency: str
    status: str
    transaction_id: str = ''


class BasePaymentProvider(ABC):
    @abstractmethod
    def initiate_payment(self, payment) -> InitiationResult: ...

    @abstractmethod
    def verify_payment(self, reference) -> VerifiedResult: ...

    @abstractmethod
    def process_callback(self, payload, signature): ...

    @abstractmethod
    def get_payment_status(self, payment) -> VerifiedResult | None: ...

    def refund_payment(self, refund):
        raise ProviderRejected('Refund submission is unavailable.')

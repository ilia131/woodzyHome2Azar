from dataclasses import dataclass

from django.conf import settings
from rest_framework.exceptions import NotFound

from .base import BasePaymentProvider
from .digipay import DigiPayProvider
from .mock import MockPaymentProvider
from .pending import ProviderNotConfigured
from .snapp_pay import SnappPayProvider
from .torob_pay import TorobPayProvider


@dataclass(frozen=True)
class Registration:
    display_name: str
    adapter: type[BasePaymentProvider]


PROVIDERS = {
    'mock': Registration('Mock Gateway', MockPaymentProvider),
    'snapp_pay': Registration('Snapp Pay', SnappPayProvider),
    'digipay': Registration('DigiPay', DigiPayProvider),
    'torob_pay': Registration('Torob Pay', TorobPayProvider),
}


def mock_enabled():
    return settings.PAYMENT_MOCK_ENABLED and settings.PAYMENT_MODE in {'development', 'test'}


def provider_for(name):
    registration = PROVIDERS.get(name)
    if not registration or (name == 'mock' and not mock_enabled()):
        raise NotFound('Payment provider unavailable.')
    if name != 'mock':
        raise ProviderNotConfigured(name)
    return registration.adapter()


def provider_availability():
    for name, registration in PROVIDERS.items():
        simulated = name == 'mock'
        enabled = simulated and mock_enabled()
        yield {
            'provider': name,
            'display_name': registration.display_name,
            'registered': True,
            'configured': simulated,
            'enabled': enabled,
            'enable_requested': settings.PAYMENT_MOCK_ENABLED if simulated else settings.PAYMENT_PROVIDER_FLAGS.get(name, False),
            'ready': False,  # This capability refers exclusively to real transactions.
            'status': ('test_ready' if enabled else 'disabled') if simulated else 'pending_credentials',
            'pending_documentation': [] if simulated else ['official merchant integration documentation'],
            'missing_configuration': [] if simulated else ['verified merchant configuration'],
        }

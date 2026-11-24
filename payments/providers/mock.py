import hmac
import re
from decimal import Decimal
from time import time
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils.crypto import salted_hmac

from payments.models import MockSession
from .base import BasePaymentProvider, InitiationResult, ProviderRejected, ProviderUnavailable, VerifiedResult


class MockPaymentProvider(BasePaymentProvider):
    def initiate_payment(self, payment):
        session, _ = MockSession.objects.get_or_create(merchant_id=payment.merchant_id, defaults={
            'reference': f'mock-{payment.merchant_id.hex}', 'amount': payment.amount, 'currency': payment.currency,
        })
        return InitiationResult(session.reference, reverse('mock-payment', kwargs={'pk': payment.pk}))

    def verify_payment(self, reference):
        session = MockSession.objects.filter(reference=reference).first()
        if session is None:
            raise ProviderRejected()
        if session.scenario in {'invalid_verification', 'delayed'}:
            raise ProviderUnavailable()
        amount = session.amount + Decimal('1.00') if session.scenario == 'invalid_amount' else session.amount
        returned_reference = 'mock-invalid' if session.scenario == 'invalid_reference' else session.reference
        return VerifiedResult(returned_reference, session.merchant_id, amount, session.currency, session.state,
                              f'{session.reference}-capture' if session.state == 'succeeded' else '')

    @staticmethod
    def sign(event, reference, timestamp):
        return salted_hmac('homeaksoria.mock.callback.v1', f'{event}:{reference}:{timestamp}',
                           secret=settings.PAYMENT_MOCK_SIGNING_KEY or settings.SECRET_KEY,
                           algorithm='sha256').hexdigest()

    def process_callback(self, payload, signature):
        try:
            event = UUID(str(payload['event_id']))
            ref = payload['reference']
            stamp = int(payload['timestamp'])
            if not re.fullmatch(r'mock-[0-9a-f]{32}', ref) or abs(time() - stamp) > 300:
                raise ValueError()
            if not hmac.compare_digest(self.sign(event, ref, stamp), signature):
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ProviderRejected() from exc
        return event, ref

    def get_payment_status(self, payment):
        session = MockSession.objects.filter(merchant_id=payment.merchant_id).first()
        return self.verify_payment(session.reference) if session else None

    @transaction.atomic
    def simulate(self, reference, scenario):
        session = MockSession.objects.select_for_update().get(reference=reference)
        if session.state == 'pending' and scenario != 'invalid_signature':
            if scenario != 'delayed':
                session.state = {'failure': 'failed', 'cancel': 'cancelled', 'timeout': 'expired'}.get(
                    scenario, 'succeeded')
            session.scenario = scenario
            session.save(update_fields=['state', 'scenario'])
        stamp = int(time())
        payload = {'event_id': str(session.event_id), 'reference': session.reference, 'timestamp': stamp}
        signature = self.sign(session.event_id, session.reference, stamp)
        return payload, 'invalid' if scenario == 'invalid_signature' else signature

    def refund_payment(self, refund):
        return f'mock-refund-{refund.payment.merchant_id.hex}-{refund.idempotency_key.hex}'

from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from core.test_catalog import CatalogTestCase
from orders.models import InventoryMovement, Order
from payments.models import MockSession, Payment, PaymentWebhookEvent
from payments.providers import provider_for
from payments.providers.base import BasePaymentProvider
from payments.providers.digipay import DigiPayProvider
from payments.providers.mock import MockPaymentProvider
from payments.providers.pending import ProviderNotConfigured
from payments.providers.registry import PROVIDERS
from payments.providers.snapp_pay import SnappPayProvider
from payments.providers.torob_pay import TorobPayProvider


PENDING = ('snapp_pay', 'digipay', 'torob_pay')


class RegistryTests(SimpleTestCase):
    @override_settings(PAYMENT_MODE='test', PAYMENT_MOCK_ENABLED=True)
    def test_all_provider_contracts_registered(self):
        expected = {'mock': MockPaymentProvider, 'snapp_pay': SnappPayProvider,
                    'digipay': DigiPayProvider, 'torob_pay': TorobPayProvider}
        self.assertEqual({name: item.adapter for name, item in PROVIDERS.items()}, expected)
        self.assertIsInstance(provider_for('mock'), MockPaymentProvider)
        for name in PENDING:
            adapter = PROVIDERS[name].adapter()
            self.assertIsInstance(adapter, BasePaymentProvider)
            for method, args in (
                ('initiate_payment', (None,)), ('verify_payment', ('ref',)),
                ('process_callback', ({}, '')), ('get_payment_status', (None,)),
                ('refund_payment', (None,)),
            ):
                with self.subTest(provider=name, operation=method):
                    with self.assertRaises(ProviderNotConfigured):
                        getattr(adapter, method)(*args)


@override_settings(PAYMENT_MODE='test', PAYMENT_MOCK_ENABLED=True)
class PendingProviderTests(CatalogTestCase):
    def test_pending_initiations_have_no_side_effect_or_mock_fallback(self):
        self.client.force_authenticate(self.user())
        for provider in PENDING:
            response = self.client.post('/api/v1/payments/initiate/', {
                'provider': provider, 'order_id': 1, 'idempotency_key': str(uuid4()),
            }, format='json')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.data['code'], 'PROVIDER_NOT_CONFIGURED')
            self.assertEqual(response.data['provider'], provider)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(MockSession.objects.exists())

    def test_callback_replay_cannot_mark_order_paid_or_consume_stock(self):
        buyer = self.user()
        order = Order.objects.create(user=buyer, order_number=uuid4().hex, subtotal='80', total_amount='80',
                                     shipping_address_snapshot={}, currency='IRR')
        for provider in PENDING:
            payment = Payment.objects.create(user=buyer, order=order, provider=provider, amount='80',
                                             currency='IRR', expires_at=order.created_at,
                                             idempotency_key=uuid4(), provider_reference=provider)
            event = str(uuid4())
            for _ in range(2):
                response = self.client.post(f'/api/v1/payments/callback/{provider}/', {
                    'event_id': event, 'reference': provider, 'status': 'succeeded',
                }, format='json')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.data['code'], 'PROVIDER_NOT_CONFIGURED')
            payment.refresh_from_db()
            self.assertEqual(payment.status, 'created')
            payment.delete()
        order.refresh_from_db()
        self.assertEqual(order.status, 'pending_payment')
        self.assertFalse(PaymentWebhookEvent.objects.exists())
        self.assertFalse(InventoryMovement.objects.exists())

    @override_settings(PAYMENT_PROVIDER_FLAGS={'snapp_pay': True})
    def test_staff_status_exposes_allowlisted_values_and_toggle_cannot_activate(self):
        url = '/api/v1/admin/payments/providers/'
        self.client.force_authenticate(self.user())
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_authenticate(self.user(2, is_staff=True, is_superuser=True))
        rows = {row['provider']: row for row in self.client.get(url).data}
        self.assertTrue(rows['snapp_pay']['enable_requested'])
        self.assertFalse(rows['snapp_pay']['enabled'])
        self.assertEqual(rows['mock']['status'], 'test_ready')
        for provider in PENDING:
            self.assertFalse(rows[provider]['configured'])
            self.assertFalse(rows[provider]['ready'])
            self.assertEqual(rows[provider]['status'], 'pending_credentials')
        self.assertNotIn('client_secret', str(rows))
        response = self.client.post('/api/v1/payments/initiate/', {
            'provider': 'snapp_pay', 'order_id': 1, 'idempotency_key': str(uuid4()),
        }, format='json')
        self.assertEqual(response.status_code, 503)

    @override_settings(PAYMENT_MODE='production', PAYMENT_MOCK_ENABLED=False)
    def test_production_does_not_expose_mock(self):
        self.client.force_authenticate(self.user())
        self.assertEqual(self.client.get('/api/v1/payments/mock/1/simulate/').status_code, 404)

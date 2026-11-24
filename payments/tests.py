from datetime import timedelta
from time import time
from unittest.mock import patch
from uuid import uuid4

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.test_catalog import CatalogTestCase
from orders.checkout import place_order
from orders.inventory import expire_order
from orders.models import CartItem, InventoryMovement, Order, Reservation
from orders import test_checkout, tests as order_tests
from .models import Payment, PaymentTransaction, PaymentWebhookEvent
from .providers.mock import MockPaymentProvider
from .providers.base import ProviderRejected, ProviderUnavailable
from .tasks import reconcile_payments


ROOT = '/api/v1/payments/'


@override_settings(PAYMENT_MODE='test', PAYMENT_MOCK_ENABLED=True)
class PaymentTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.buyer = self.user()
        self.client.force_authenticate(self.buyer)
        self.address = test_checkout.CheckoutTests.make_address(self.buyer)
        CartItem.objects.create(user=self.buyer, product=self.product, quantity=1)
        self.order = place_order(self.buyer, self.address.pk)
        self.data = {'order_id': self.order.pk, 'provider': 'mock', 'idempotency_key': str(uuid4())}

    def initiate(self, **extra):
        return self.client.post(ROOT+'initiate/', {**self.data, **extra}, format='json')

    def simulate(self, payment, scenario):
        return self.client.post(f'{ROOT}mock/{payment}/simulate/', {'scenario': scenario}, format='json')

    def test_initiation_database_amount_idempotency_and_active_attempt(self):
        response = self.initiate(amount='0.01')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['amount'], '80.00')
        self.assertEqual(self.initiate().data['id'], response.data['id'])
        self.assertEqual(self.initiate(idempotency_key=str(uuid4())).status_code, 409)
        self.assertEqual(self.client.get(ROOT).data['count'], 1)
        self.assertEqual(self.client.get(f"{ROOT}{response.data['id']}/status/").data['status'], 'pending')
        self.assertNotIn('idempotency_key', response.data)
        self.assertNotIn('merchant_id', response.data)

    def test_isolation_anonymous_and_admin_routes(self):
        payment = self.initiate().data['id']
        self.assertEqual(self.client.get('/api/v1/admin/payments/').status_code, 403)
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.initiate().status_code, 404)
        self.assertEqual(self.client.get(f'{ROOT}{payment}/').status_code, 404)
        self.assertEqual(self.simulate(payment, 'success').status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.initiate().status_code, 401)
        staff = self.user(3, is_staff=True, is_superuser=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get('/api/v1/admin/payments/').data['count'], 1)
        self.assertEqual(self.client.patch(f'/api/v1/admin/payments/{payment}/', {'status':'succeeded'}).status_code, 405)

    def test_success_replay_consumes_hold_once(self):
        payment = self.initiate().data['id']
        self.assertEqual(self.simulate(payment, 'success').data['status'], 'succeeded')
        self.assertEqual(self.simulate(payment, 'failure').data['status'], 'succeeded')
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(InventoryMovement.objects.filter(kind='consume').count(), 1)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
        self.assertEqual(PaymentTransaction.objects.filter(transaction_type='capture').count(), 1)

    def test_invalid_signature_and_unknown_authority(self):
        payment = self.initiate().data['id']
        self.assertEqual(self.simulate(payment, 'invalid_signature').status_code, 403)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 0)
        event, stamp, ref = uuid4(), int(time()), f'mock-{uuid4().hex}'
        response = self.client.post(ROOT+'callback/mock/', {'event_id': str(event), 'reference':ref, 'timestamp':stamp},
                                    format='json', HTTP_X_PAYMENT_SIGNATURE=MockPaymentProvider.sign(event, ref, stamp))
        self.assertEqual(response.status_code, 404)

    def test_invalid_amount_requires_review_without_consumption(self):
        payment = self.initiate().data['id']
        self.assertEqual(self.simulate(payment, 'invalid_amount').data['status'], 'requires_review')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'payment_review')
        self.assertFalse(InventoryMovement.objects.filter(kind='consume').exists())

    def test_provider_failure_and_uncertain_initiation(self):
        with patch.object(MockPaymentProvider, 'initiate_payment', side_effect=ProviderRejected):
            self.assertEqual(self.initiate().data['status'], 'failed')
        self.data['idempotency_key'] = str(uuid4())
        with patch.object(MockPaymentProvider, 'initiate_payment', side_effect=ProviderUnavailable):
            self.assertEqual(self.initiate().data['status'], 'processing')
        self.assertEqual(self.initiate(idempotency_key=str(uuid4())).status_code, 409)
        reconcile_payments.run()
        self.assertEqual(Payment.objects.get(idempotency_key=self.data['idempotency_key']).status, 'pending')

    def test_local_deadline_does_not_allow_second_unknown_provider_attempt(self):
        payment = self.initiate().data['id']
        Payment.objects.filter(pk=payment).update(expires_at=timezone.now()-timedelta(seconds=1))
        reconcile_payments.run()
        self.assertEqual(Payment.objects.get(pk=payment).status, 'expired')
        self.data['idempotency_key'] = str(uuid4())
        self.assertEqual(self.initiate().status_code, 409)
        self.assertEqual(self.simulate(payment, 'timeout').data['status'], 'expired')
        self.assertEqual(self.initiate().status_code, 201)


    def expire_hold(self):
        stamp = timezone.now()
        self.order.reservations.update(reserved_at=stamp-timedelta(minutes=20), expires_at=stamp-timedelta(seconds=1))
        expire_order(self.order.pk)

    def test_late_payment_reacquires_stock_and_keeps_expired_history(self):
        payment = self.initiate().data['id']
        self.expire_hold()
        self.assertEqual(self.simulate(payment, 'success').data['status'], 'succeeded')
        self.assertCountEqual(self.order.reservations.values_list('status', flat=True), ['expired', 'consumed'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_late_payment_without_stock_requires_review(self):
        payment = self.initiate().data['id']
        self.expire_hold()
        self.product.stock = 0
        self.product.save(update_fields=['stock'])
        self.assertEqual(self.simulate(payment, 'success').data['status'], 'requires_review')
        self.assertFalse(self.order.reservations.filter(status=Reservation.Status.CONSUMED).exists())

    def test_expired_and_cancelled_orders_reject_initiation(self):
        self.expire_hold()
        self.assertEqual(self.initiate().status_code, 409)

    @override_settings(PAYMENT_MODE='production', PAYMENT_MOCK_ENABLED=True)
    def test_production_defense_in_depth(self):
        self.assertEqual(self.initiate().status_code, 404)
        self.assertEqual(self.simulate(1, 'success').status_code, 404)

    def test_mock_failure_cancel_timeout_and_delay(self):
        for scenario, expected in (('failure','failed'), ('cancel','cancelled'), ('timeout','expired')):
            self.data['idempotency_key'] = str(uuid4())
            payment = self.initiate().data['id']
            self.assertEqual(self.simulate(payment, scenario).data['status'], expected)
        self.data['idempotency_key'] = str(uuid4())
        payment = self.initiate().data['id']
        self.assertEqual(self.simulate(payment, 'delayed').data['status'], 'processing')
        self.assertEqual(self.simulate(payment, 'success').data['status'], 'succeeded')

    def test_reference_and_verification_failure(self):
        payment = self.initiate().data['id']
        self.assertEqual(self.simulate(payment, 'invalid_verification').data['status'], 'processing')
        self.assertFalse(InventoryMovement.objects.filter(kind='consume').exists())
        self.assertTrue(PaymentWebhookEvent.objects.filter(status='retry').exists())
        # A mismatched reference is checked independently from signature.
        attempt = Payment.objects.get(pk=payment)
        from dataclasses import replace
        from payments.services import apply_result

        valid = MockPaymentProvider().initiate_payment(attempt)
        with patch('payments.providers.mock.MockPaymentProvider.verify_payment') as verify:
            from payments.providers.base import VerifiedResult
            verify.return_value = VerifiedResult(valid.reference, attempt.merchant_id, attempt.amount,
                                                 attempt.currency, 'succeeded', 'example')
            result = replace(verify.return_value, reference='mock-invalid')
            self.assertEqual(apply_result(attempt.pk, result).status, 'requires_review')

    def test_partial_refund_request_is_audited_and_does_not_restore_stock(self):
        payment = self.initiate().data['id']
        self.simulate(payment, 'success')
        self.client.force_authenticate(self.user(2, is_staff=True, is_superuser=True))
        path = f'/api/v1/admin/payments/{payment}/refunds/'
        data = {'idempotency_key': str(uuid4()), 'amount':'20.00'}
        response = self.client.post(path, data, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'requested')
        self.assertEqual(self.client.post(path, data, format='json').data['id'], response.data['id'])
        data['idempotency_key'] = str(uuid4())
        data['amount'] = '61'
        self.assertEqual(self.client.post(path, data, format='json').status_code, 409)
        simulate = f"{path}{response.data['id']}/simulate/"
        simulated = self.client.patch(simulate)
        self.assertEqual(simulated.data['status'], 'simulated')
        self.assertTrue(simulated.data['provider_reference'].startswith('mock-refund-'))
        self.assertEqual(self.client.patch(simulate).status_code, 200)
        self.assertEqual(PaymentTransaction.objects.filter(transaction_type='refund_simulation').count(), 1)
        self.assertFalse(InventoryMovement.objects.filter(kind__in=['release','expire']).exists())




@override_settings(PAYMENT_MODE='test', PAYMENT_MOCK_ENABLED=True)
class ConcurrentPaymentTests(order_tests.ConcurrentCommerceCase):
    def setUp(self):
        super().setUp()
        from payments.services import initiate

        address = test_checkout.CheckoutTests.make_address(self.user)
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        self.order = place_order(self.user, address.pk)
        self.payment, _ = initiate(self.user, self.order.pk, 'mock', uuid4())
        self.payload, self.signature = MockPaymentProvider().simulate(self.payment.provider_reference, 'success')

    def race(self, *callbacks):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections

        barrier = Barrier(len(callbacks), timeout=10)

        def run(fn):
            try:
                barrier.wait()
                return fn()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
            return list(pool.map(run, callbacks))

    def callback(self):
        from payments.services import callback

        return callback('mock', self.payload, self.signature).status

    def test_duplicate_callbacks_and_verification_settle_once(self):
        self.assertEqual(self.race(self.callback, self.callback), ['succeeded'] * 2)
        self.assertEqual(InventoryMovement.objects.filter(kind='consume').count(), 1)
        self.assertEqual(PaymentTransaction.objects.filter(transaction_type='capture').count(), 1)

    def test_callback_races_expiration(self):
        now = timezone.now()
        self.order.reservations.update(reserved_at=now-timedelta(minutes=20), expires_at=now-timedelta(seconds=1))
        results = self.race(self.callback, lambda: expire_order(self.order.pk))
        self.assertEqual(results[0], 'succeeded')
        self.assertEqual(InventoryMovement.objects.filter(kind='expire').count(), 1)
        self.assertEqual(InventoryMovement.objects.filter(kind='consume').count(), 1)

    def test_callback_races_cancellation(self):
        def cancel():
            client = APIClient()
            client.force_authenticate(self.user)
            return client.post(f'/api/v1/orders/{self.order.pk}/cancel/').status_code

        status, code = self.race(self.callback, cancel)
        self.assertIn((status, code), {('succeeded', 409), ('requires_review', 200)})
        self.assertEqual(InventoryMovement.objects.filter(kind='consume').count(), int(code == 409))
        self.assertEqual(InventoryMovement.objects.filter(kind='release').count(), int(code == 200))

    def test_callback_and_revision_based_stock_adjustment(self):
        from orders.inventory import adjust_available, stock_revision, InventoryConflict

        now = timezone.now()
        self.order.reservations.update(reserved_at=now-timedelta(minutes=20), expires_at=now-timedelta(seconds=1))
        revision = stock_revision(self.product.pk)

        def adjust():
            try:
                adjust_available(self.product.pk, self.user, target=1, expected_revision=revision, operation_id=uuid4())
                return 'updated'
            except InventoryConflict:
                return 'stale'

        status, adjustment = self.race(self.callback, adjust)
        self.assertEqual(status, 'succeeded')
        self.assertIn(adjustment, {'stale', 'updated'})
        self.assertEqual(InventoryMovement.objects.filter(kind='consume').count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, int(adjustment == 'updated'))

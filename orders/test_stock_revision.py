from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from django.db import connections, transaction
from rest_framework.test import APIClient

from accounts.models import User
from orders.inventory import adjust_available, stock_revision
from orders.models import CartItem, InventoryMovement
from . import test_checkout
from .tests import ConcurrentCommerceCase


class StockRevisionTests(ConcurrentCommerceCase):
    def setUp(self):
        super().setUp()
        self.operator = User.objects.create_user('09121234569', is_staff=True, is_superuser=True)
        self.adjust_url = f'/api/v1/admin/inventory/products/{self.product.pk}/adjust/'
        self.catalog_url = f'/api/v1/admin/products/{self.product.pk}/'
        self.client = APIClient()
        self.client.force_authenticate(self.operator)

    def test_absolute_adjustment_ledger_input_and_replay(self):
        revision = stock_revision(self.product.pk)
        data = {'target': 3, 'expected_revision': revision, 'operation_id': str(uuid4())}
        first = self.client.post(self.adjust_url, data, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['available_delta'], 2)
        self.assertEqual(first.data['available_after'], 3)
        retry = self.client.post(self.adjust_url, data, format='json')
        self.assertEqual(retry.data['id'], first.data['id'])
        self.assertEqual(self.client.post(self.adjust_url, {**data, 'target': -1}).status_code, 400)
        self.assertEqual(self.client.post(self.adjust_url, {**data, 'target': 4}).status_code, 409)
        self.assertEqual(InventoryMovement.objects.filter(kind='adjust').count(), 1)

    def test_catalog_requires_revision_and_uses_inventory_ledger(self):
        self.assertEqual(self.client.patch(self.catalog_url, {'stock': 7}).status_code, 409)
        current = self.client.get(self.catalog_url).data
        result = self.client.patch(self.catalog_url, {'stock': 7, 'stock_revision': current['stock_revision']})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['stock'], 7)
        self.assertEqual(InventoryMovement.objects.get(kind='adjust').available_delta, 6)
        self.assertEqual(self.client.patch(self.catalog_url, {'description': 'Revised'}).status_code, 200)
        self.assertEqual(InventoryMovement.objects.filter(kind='adjust').count(), 1)

    def test_adjustment_waiting_for_checkout_cannot_restore_reserved_stock(self):
        from orders.checkout import place_order

        address = test_checkout.CheckoutTests.make_address(self.user)
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        revision = stock_revision(self.product.pk)
        started = Event()

        def stale_adjustment():
            try:
                client = APIClient()
                client.force_authenticate(self.operator)
                started.set()
                return client.patch(self.catalog_url, {'stock': 1, 'stock_revision': revision}).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                place_order(self.user, address.pk)
                request = pool.submit(stale_adjustment)
                self.assertTrue(started.wait(5))
            self.assertEqual(request.result(timeout=10), 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertEqual(InventoryMovement.objects.filter(kind='adjust').count(), 0)

    def test_two_simultaneous_absolute_adjustments_serialize(self):
        data = {'target': 3, 'expected_revision': stock_revision(self.product.pk), 'operation_id': str(uuid4())}
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                adjust_available(self.product.pk, self.operator, target=2,
                                 expected_revision=data['expected_revision'], operation_id=uuid4())

                def request():
                    try:
                        client = APIClient()
                        client.force_authenticate(self.operator)
                        return client.post(self.adjust_url, data, format='json').status_code
                    finally:
                        connections.close_all()

                second = pool.submit(request)
            self.assertEqual(second.result(timeout=10), 409)
        self.assertEqual(list(InventoryMovement.objects.values_list('available_delta', flat=True)), [1])

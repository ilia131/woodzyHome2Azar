from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AuditLog
from products.models import Product
from .inventory import consume_order_reservations
from .models import CartItem, InventoryMovement, Order, Reservation
from .tasks import expire_reservations
from . import test_checkout
from .test_checkout import ORDERS
from .tests import ConcurrentCommerceCase
from core.test_catalog import CatalogTestCase


class InventoryTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.buyer = self.user()
        self.client.force_authenticate(self.buyer)
        self.address = test_checkout.CheckoutTests.make_address(self.buyer)

    def place(self, qty=1):
        CartItem.objects.create(user=self.buyer, product=self.product, quantity=qty)
        return self.client.post(ORDERS, {'address_id': self.address.pk}, format='json')

    @staticmethod
    def make_due(order):
        now = timezone.now()
        order.reservations.update(reserved_at=now - timedelta(minutes=20), expires_at=now - timedelta(seconds=1))

    @override_settings(INVENTORY_RESERVATION_SECONDS=90)
    def test_reservation_dates_quantities_ledger_and_database_guards(self):
        response = self.place(3)
        self.assertEqual(response.status_code, 201, response.data)
        row = Reservation.objects.get()
        self.assertEqual(row.quantity, row.item.quantity)
        self.assertEqual(row.expires_at - row.reserved_at, timedelta(seconds=90))
        reserve = InventoryMovement.objects.get(kind='reserve')
        self.assertEqual((reserve.available_delta, reserve.available_after), (-3, 1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.objects.create(product=self.product, product_id_snapshot=self.product.pk, reservation=row,
                                             kind='reserve', quantity=1, available_delta=-1, available_after=0,
                                             operation_key='different-key')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=self.product.pk).update(stock=-1)

    def test_failure_after_first_reservation_rolls_back_all_lines(self):
        second = Product.objects.create(title='second', slug='second', sku='SECOND', category=self.category,
                                        price=1, stock=2)
        CartItem.objects.create(user=self.buyer, product=second, quantity=1)
        manager = InventoryMovement.objects
        create = manager.create

        def fail_second(**kwargs):
            if kwargs['product'].pk == second.pk:
                raise IntegrityError('Injected ledger error')
            return create(**kwargs)

        self.client.raise_request_exception = False
        with patch.object(manager, 'create', side_effect=fail_second):
            self.assertEqual(self.place(1).status_code, 500)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Reservation.objects.exists())
        self.assertFalse(InventoryMovement.objects.exists())
        self.assertEqual(CartItem.objects.count(), 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)

    def test_cancel_is_owned_and_releases_once(self):
        order_id = self.place(2).data['id']
        url = f'{ORDERS}{order_id}/cancel/'
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.force_authenticate(self.buyer)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'cancelled')
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(Reservation.objects.get().status, 'released')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(InventoryMovement.objects.get(kind='release').available_delta, 2)
        self.assertTrue(AuditLog.objects.filter(action='order_cancel', actor=self.buyer).exists())

    def test_overdue_cancellation_expires_inline_and_task_is_idempotent(self):
        order = Order.objects.get(pk=self.place().data['id'])
        self.make_due(order)
        self.assertEqual(self.client.post(f'{ORDERS}{order.pk}/cancel/').status_code, 409)
        order.refresh_from_db()
        self.assertEqual(order.status, 'expired')
        self.assertEqual(expire_reservations.run(), 0)
        self.assertEqual(InventoryMovement.objects.filter(kind='expire').count(), 1)
        self.assertTrue(AuditLog.objects.filter(action='inventory_expire').exists())

    def test_expiry_worker_updates_pending_but_preserves_other_status_and_legacy_orders(self):
        first = Order.objects.get(pk=self.place().data['id'])
        second = Order.objects.get(pk=self.place().data['id'])
        Order.objects.filter(pk=second.pk).update(status=Order.Status.PROCESSING)
        for order in (first, second):
            self.make_due(order)
        self.assertEqual(expire_reservations.run(), 2)
        self.assertEqual(expire_reservations.run(), 0)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.status, second.status), ('expired', 'processing'))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(Reservation.objects.filter(status='expired').count(), 2)
        # An order predating the reservation migration has no hold to release.
        Reservation.objects.filter(order=first).update(status='released')
        Order.objects.filter(pk=first.pk).update(status='pending_payment')
        self.assertEqual(self.client.post(f'{ORDERS}{first.pk}/cancel/').status_code, 409)

    def test_checkout_reclaims_overdue_stock_before_beat(self):
        order = Order.objects.get(pk=self.place(4).data['id'])
        self.make_due(order)
        self.assertEqual(self.place(4).status_code, 201)
        order.refresh_from_db()
        self.assertEqual(order.status, 'expired')

    def test_internal_consumption_has_no_second_deduction(self):
        order = Order.objects.get(pk=self.place(2).data['id'])
        consume_order_reservations(order.pk)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(Reservation.objects.get().status, 'consumed')
        self.assertEqual(InventoryMovement.objects.get(kind='consume').available_delta, 0)
        self.assertEqual(self.client.post(f'{ORDERS}{order.pk}/cancel/').status_code, 409)

    def test_admin_permissions_filters_and_idempotent_adjustment(self):
        order = Order.objects.get(pk=self.place().data['id'])
        call_command('provision_roles', verbosity=0)
        protected = self.user(2, is_staff=True)
        protected.groups.add(Group.objects.get(name='Order Manager'))
        product_manager = self.user(3, is_staff=True)
        product_manager.groups.add(Group.objects.get(name='Product Manager'))
        url = f'/api/v1/admin/inventory/products/{self.product.pk}/adjust/'
        data = {'delta': 2, 'operation_id': str(uuid4())}
        self.assertEqual(self.client.get('/api/v1/admin/orders/').status_code, 403)
        self.client.force_authenticate(protected)
        result = self.client.get('/api/v1/admin/orders/', {'order_number': order.order_number,
                                                           'status': 'pending_payment', 'user': self.buyer.pk})
        self.assertEqual(result.data['count'], 1)
        self.assertEqual(result.data['results'][0]['reservations'][0]['status'], 'active')
        self.assertEqual(self.client.get(f'/api/v1/admin/orders/{order.pk}/').status_code, 200)
        self.assertEqual(self.client.post(url, data, format='json').status_code, 403)
        self.client.force_authenticate(product_manager)
        result = self.client.post(url, data, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.client.post(url, data, format='json').data['id'], result.data['id'])
        self.assertEqual(self.client.post(url, {**data, 'delta': 3}, format='json').status_code, 409)
        self.assertEqual(self.client.post(url, {'delta': -6, 'operation_id': str(uuid4())},
                                          format='json').status_code, 409)
        self.assertEqual(self.client.get('/api/v1/admin/inventory/movements/', {'kind': 'adjust'}).data['count'], 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)


class ConcurrentInventoryTests(ConcurrentCommerceCase):
    def race(self, *callbacks):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections

        barrier = Barrier(len(callbacks), timeout=10)

        def run(callback):
            try:
                barrier.wait()
                return callback()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(callbacks)) as pool:
            return list(pool.map(run, callbacks))

    @staticmethod
    def post(user, url, data):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(url, data, format='json').status_code

    def test_final_unit_reserved_by_only_one_concurrent_buyer(self):
        purchasers = (self.user, self.other)
        addresses = [test_checkout.CheckoutTests.make_address(user) for user in purchasers]
        for user in purchasers:
            CartItem.objects.create(user=user, product=self.product, quantity=1)
        results = self.race(
            lambda: self.post(self.user, ORDERS, {'address_id': addresses[0].pk}),
            lambda: self.post(self.other, ORDERS, {'address_id': addresses[1].pk}),
        )
        self.assertCountEqual(results, [201, 409])
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(CartItem.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_reversed_multi_product_carts_lock_in_id_order(self):
        from .inventory import lock_products

        Product.objects.filter(pk=self.product.pk).update(stock=2)
        second = Product.objects.create(title='Other', slug='other', sku='OTHER', price=5,
                                        category=self.product.category, stock=2)
        addresses = [test_checkout.CheckoutTests.make_address(user) for user in (self.user, self.other)]
        for user, products in ((self.user, (self.product, second)), (self.other, (second, self.product))):
            for product in products:
                CartItem.objects.create(user=user, product=product, quantity=1)
        locked_ids = []

        def record_lock(ids):
            rows = lock_products(ids)
            locked_ids.append(list(rows))
            return rows

        with patch('orders.checkout.lock_products', side_effect=record_lock):
            self.assertEqual(self.race(
                lambda: self.post(self.user, ORDERS, {'address_id': addresses[0].pk}),
                lambda: self.post(self.other, ORDERS, {'address_id': addresses[1].pk}),
            ), [201, 201])
        self.assertEqual(locked_ids, [[self.product.pk, second.pk]] * 2)
        self.assertEqual(Reservation.objects.count(), 4)
        self.assertEqual(list(Product.objects.order_by('pk').values_list('stock', flat=True)), [0, 0])

    def test_cancel_and_two_workers_release_due_hold_once(self):
        address = test_checkout.CheckoutTests.make_address(self.user)
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        self.assertEqual(self.post(self.user, ORDERS, {'address_id': address.pk}), 201)
        order = Order.objects.get()
        InventoryTests.make_due(order)
        results = self.race(
            lambda: self.post(self.user, f'{ORDERS}{order.pk}/cancel/', {}),
            expire_reservations.run,
            expire_reservations.run,
        )
        self.assertEqual(results[0], 409)
        self.assertEqual(InventoryMovement.objects.filter(kind='expire').count(), 1)
        self.assertEqual(InventoryMovement.objects.filter(kind='release').count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

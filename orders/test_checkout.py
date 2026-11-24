from unittest.mock import patch

from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from core.models import AuditLog
from core.test_catalog import CatalogTestCase
from products.models import Product
from .models import Address, CartItem, Order, OrderItem
from .tests import ADDRESS, ConcurrentCommerceCase


ORDERS = '/api/v1/orders/'


class CheckoutTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.customer = self.user()
        self.client.force_authenticate(self.customer)
        self.address = self.make_address(self.customer)

    @staticmethod
    def make_address(user):
        return Address.objects.create(user=user, **{
            **ADDRESS, 'recipient_phone': '+989121234567', 'postal_code': '1234567890',
        })

    def cart_line(self, quantity=1, *, product=None, user=None):
        return CartItem.objects.create(user=user or self.customer, product=product or self.product, quantity=quantity)

    def checkout(self, address_id=None, **extra):
        return self.client.post(ORDERS, {'address_id': self.address.pk if address_id is None else address_id, **extra},
                                format='json')

    def test_create_order_from_multiple_products_and_clear_only_own_cart(self):
        other = self.user(2)
        second = Product.objects.create(title='Chair', slug='chair', sku='CHAIR-1', category=self.category,
                                        price=55, stock=8)
        self.cart_line(2)
        self.cart_line(3, product=second)
        other_row = self.cart_line(user=other)
        response = self.checkout()
        self.assertEqual(response.status_code, 201, response.data)
        result = response.data
        self.assertEqual(result['status'], 'pending_payment')
        self.assertEqual(result['subtotal'], '325.00')
        self.assertEqual(result['total_amount'], '325.00')
        self.assertEqual(result['shipping_amount'], '0.00')
        self.assertEqual(result['discount_amount'], '0.00')
        self.assertEqual([item['line_total'] for item in result['items']], ['160.00', '165.00'])
        self.assertNotIn('user', result)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(list(CartItem.objects.values_list('pk', flat=True)), [other_row.pk])
        self.product.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((self.product.stock, second.stock), (2, 5))
        event = AuditLog.objects.get(action='order_create')
        self.assertEqual(event.actor_id, self.customer.pk)
        self.assertEqual(event.object_id, str(result['id']))
        self.assertEqual(event.model_label, 'orders.order')
        self.assertEqual(event.metadata, {'order_number': result['order_number'], 'item_count': 2})

    def test_orders_require_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.checkout().status_code, 401)
        self.assertEqual(self.client.get(ORDERS).status_code, 401)
        self.assertEqual(self.client.get(f'{ORDERS}1/').status_code, 401)

    def test_empty_cart_conflict(self):
        self.assertEqual(self.checkout().status_code, 409)
        self.assertFalse(Order.objects.exists())

    def test_invalid_and_foreign_addresses_are_rejected(self):
        self.cart_line()
        self.assertEqual(self.checkout(address_id=0).status_code, 400)
        self.assertEqual(self.checkout(address_id=self.address.pk + 1000).status_code, 404)
        foreign = self.make_address(self.user(2))
        self.assertEqual(self.checkout(address_id=foreign.pk).status_code, 404)
        self.assertEqual(CartItem.objects.count(), 1)
        self.assertFalse(Order.objects.exists())

    def test_inactive_and_hidden_products_are_rejected_without_consuming_cart(self):
        self.cart_line()
        for target in (self.product, self.root):
            target.is_active = False
            target.save(update_fields=['is_active'])
            self.assertEqual(self.checkout().status_code, 409)
            self.assertEqual(CartItem.objects.count(), 1)
            self.assertFalse(Order.objects.exists())
            target.is_active = True
            target.save(update_fields=['is_active'])

    def test_zero_quantity_constraint_and_stale_stock_rejection(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.cart_line(0)
        self.cart_line(4)
        for stock in (2, 0):
            self.product.stock = stock
            self.product.save(update_fields=['stock'])
            self.assertEqual(self.checkout().status_code, 409)
            self.assertFalse(Order.objects.exists())
            self.assertEqual(CartItem.objects.get().quantity, 4)

    def test_client_financial_fields_are_refused_and_current_price_is_used(self):
        self.cart_line(2)
        for field in ('unit_price', 'total_amount', 'subtotal', 'product_title', 'user'):
            self.assertEqual(self.checkout(**{field: '1'}).status_code, 400)
        self.assertFalse(Order.objects.exists())
        self.product.discount_price = '62.50'
        self.product.save(update_fields=['discount_price'])
        result = self.checkout()
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['items'][0]['unit_price'], '62.50')
        self.assertEqual(result.data['total_amount'], '125.00')

    def test_product_and_address_snapshots_survive_changes_and_deletion(self):
        self.product.main_image = 'products/original.jpg'
        self.product.save(update_fields=['main_image'])
        self.cart_line()
        created = self.checkout().data
        self.product.title = 'Renamed'
        self.product.sku = 'UPDATED'
        self.product.discount_price = '60.00'
        self.product.main_image = 'products/replacement.jpg'
        self.product.is_active = False
        self.product.save(update_fields=['title', 'sku', 'discount_price', 'main_image', 'is_active'])
        url = f"{ORDERS}{created['id']}/"
        expected = created['items'][0]
        self.assertEqual(self.client.get(url).data['items'][0], expected)
        self.address.city = 'ری'
        self.address.save(update_fields=['city'])
        self.assertEqual(self.client.get(url).data['shipping_address_snapshot'], created['shipping_address_snapshot'])
        self.address.delete()
        self.assertEqual(self.client.post(f'{url}cancel/').status_code, 200)
        self.product.delete()
        historical = self.client.get(url).data
        self.assertIsNone(historical['shipping_address'])
        self.assertEqual(historical['shipping_address_snapshot'], created['shipping_address_snapshot'])
        self.assertEqual(historical['items'][0], {**expected, 'product_id': None})
        self.assertEqual(historical['items'][0]['product_main_image'], 'products/original.jpg')

    def test_order_item_write_failure_rolls_back_order_and_preserves_cart(self):
        self.cart_line()
        self.client.raise_request_exception = False
        with patch('orders.checkout.OrderItem.objects.bulk_create', side_effect=IntegrityError('test failure')):
            self.assertEqual(self.checkout().status_code, 500)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(OrderItem.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action='order_create').exists())
        self.assertEqual(CartItem.objects.count(), 1)

    def test_order_list_is_paginated_and_owner_scoped(self):
        for _ in range(2):
            self.cart_line()
            latest = self.checkout().data
        listing = self.client.get(ORDERS, {'page_size': 1})
        self.assertEqual(listing.data['count'], 2)
        self.assertEqual(listing.data['results'][0]['id'], latest['id'])
        self.assertTrue(listing.data['next'])
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.client.get(ORDERS, {'user': self.customer.pk}).data['count'], 0)
        self.assertEqual(self.client.get(f"{ORDERS}{latest['id']}/").status_code, 404)


class ConcurrentCheckoutTests(ConcurrentCommerceCase):
    def test_two_checkouts_cannot_consume_the_same_cart(self):
        address = CheckoutTests.make_address(self.user)
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        results = self.post_concurrently(ORDERS, {'address_id': address.pk}, (self.user, self.user))
        self.assertEqual(results, [201, 409])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='order_create').count(), 1)
        self.assertFalse(CartItem.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

    def test_different_carts_cannot_reserve_the_same_available_unit(self):
        first_address = CheckoutTests.make_address(self.user)
        second_address = CheckoutTests.make_address(self.other)
        CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        CartItem.objects.create(user=self.other, product=self.product, quantity=1)
        users = ((self.user, first_address), (self.other, second_address))
        client = APIClient()
        for (user, address), expected in zip(users, (201, 409)):
            client.force_authenticate(user)
            self.assertEqual(client.post(ORDERS, {'address_id': address.pk}, format='json').status_code, expected)
        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)

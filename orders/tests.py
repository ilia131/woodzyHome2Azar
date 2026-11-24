from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from core.models import AuditLog
from core.test_catalog import CatalogTestCase
from products.models import Product
from categories.models import Category
from .models import Address, CartItem


ADDRESS = {
    'recipient_name': 'علی رضایی', 'recipient_phone': '۰۹۱۲۱۲۳۴۵۶۷',
    'province': 'تهران', 'city': 'تهران', 'address_line': 'خیابان اصلی، پلاک ۱',
    'postal_code': '۱۲۳۴۵-۶۷۸۹۰',
}
ADDRESSES = '/api/v1/addresses/'
CART = '/api/v1/cart/'
CART_ITEMS = '/api/v1/cart/items/'


class AddressTests(CatalogTestCase):
    def test_address_crud_default_promotion_and_audit(self):
        user = self.user()
        self.client.force_authenticate(user)
        first = self.client.post(ADDRESSES, ADDRESS, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['recipient_phone'], '+989121234567')
        self.assertEqual(first.data['postal_code'], '1234567890')
        self.assertTrue(first.data['is_default'])
        second = self.client.post(ADDRESSES, {**ADDRESS, 'label': 'Work'}, format='json')
        self.assertEqual(second.status_code, 201)
        self.assertFalse(second.data['is_default'])
        first_url = f"{ADDRESSES}{first.data['id']}/"
        second_url = f"{ADDRESSES}{second.data['id']}/"
        self.assertEqual(self.client.patch(first_url, {'is_default': False}).status_code, 400)
        self.assertEqual(self.client.patch(second_url, {'is_default': True, 'city': 'ری'}).status_code, 200)
        self.assertEqual(self.client.get(second_url).data['city'], 'ری')
        addresses = self.client.get(ADDRESSES, {'page_size': 1})
        self.assertEqual(addresses.data['count'], 2)
        self.assertEqual(addresses.data['results'][0]['id'], second.data['id'])
        self.assertIn('no-store', addresses['Cache-Control'])
        self.assertEqual(self.client.delete(second_url).status_code, 204)
        self.assertTrue(self.client.get(first_url).data['is_default'])
        self.assertEqual(list(AuditLog.objects.filter(actor=user).order_by('pk').values_list('action', flat=True)), [
            'address_create', 'address_create', 'address_unset_default', 'address_update', 'address_delete',
            'address_set_default',
        ])

    def test_address_validation_and_ownership(self):
        self.assertEqual(self.client.get(ADDRESSES).status_code, 401)
        owner, other = self.user(), self.user(2)
        self.client.force_authenticate(owner)
        for invalid in ({'postal_code': '123'}, {'recipient_phone': '123'}, {'recipient_name': ' '}):
            self.assertEqual(self.client.post(ADDRESSES, {**ADDRESS, **invalid}).status_code, 400)
        result = self.client.post(ADDRESSES, {**ADDRESS, 'user': other.pk}, format='json')
        self.assertEqual(Address.objects.get().user_id, owner.pk)
        url = f"{ADDRESSES}{result.data['id']}/"
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(ADDRESSES, {'user': owner.pk}).data['count'], 0)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {'city': 'Other'}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)


class CartTests(CatalogTestCase):
    def post_item(self, quantity, product=None):
        return self.client.post(CART_ITEMS, {'product_id': (product or self.product).pk, 'quantity': quantity},
                                format='json')

    def test_cart_add_retry_edit_delete_live_price_and_audit(self):
        user = self.user()
        self.client.force_authenticate(user)
        first = self.post_item(2)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['unit_price'], '80.00')
        self.assertEqual(first.data['line_total'], '160.00')
        self.assertEqual(first.data['product_title'], self.product.title)
        self.assertEqual(first.data['availability'], 'available')
        duplicate = self.post_item(2)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.data['id'], first.data['id'])
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(self.post_item(1).data['quantity'], 1)
        url = f"{CART_ITEMS}{first.data['id']}/"
        updated = self.client.patch(url, {'quantity': 3})
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data['quantity'], 3)
        self.product.discount_price = '60.00'
        self.product.save(update_fields=['discount_price'])
        result = self.client.get(CART)
        self.assertIn('no-store', result['Cache-Control'])
        self.assertEqual(result.data['results'][0]['line_total'], '180.00')
        self.assertEqual(result.data['summary']['subtotal'], '180.00')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(CART).data['count'], 0)
        self.assertEqual(list(AuditLog.objects.filter(actor=user).order_by('pk').values_list('action', flat=True)),
                         ['cart_add', 'cart_update', 'cart_update', 'cart_remove'])

    def test_stock_and_visibility_are_revalidated_and_hidden_lines_stay_removable(self):
        self.client.force_authenticate(self.user())
        self.assertEqual(self.post_item(0).status_code, 400)
        self.assertEqual(self.post_item(5).status_code, 409)
        self.assertFalse(CartItem.objects.exists())
        first = self.post_item(4)
        url = f"{CART_ITEMS}{first.data['id']}/"
        self.product.stock = 2
        self.product.save(update_fields=['stock'])
        result = self.client.get(CART).data
        self.assertEqual(result['results'][0]['availability'], 'insufficient_stock')
        self.assertEqual(result['summary']['subtotal'], '0.00')
        self.assertEqual(self.client.patch(url, {'quantity': 3}).status_code, 409)
        self.product.stock = 0
        self.product.save(update_fields=['stock'])
        self.assertEqual(self.client.get(CART).data['results'][0]['availability'], 'out_of_stock')
        self.root.is_active = False
        self.root.save(update_fields=['is_active'])
        item = self.client.get(CART).data['results'][0]
        self.assertEqual(item['availability'], 'not_visible')
        self.assertIsNone(item['unit_price'])
        self.assertIsNone(item['product_title'])
        self.assertEqual(self.post_item(1).status_code, 404)
        self.assertEqual(self.client.patch(url, {'quantity': 1}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 204)

    def test_cart_ownership_guest_access_and_pagination(self):
        self.assertEqual(self.client.get(CART).status_code, 401)
        self.assertEqual(self.post_item(1).status_code, 401)
        owner, other = self.user(), self.user(2)
        self.client.force_authenticate(owner)
        first = self.post_item(1)
        second_product = Product.objects.create(title='Second', slug='second', sku='S-2', category=self.category,
                                                price=100, stock=1)
        second = self.post_item(1, second_product)
        response = self.client.get(CART, {'page_size': 1, 'user': other.pk})
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], second.data['id'])
        self.assertEqual(response.data['summary']['subtotal'], '180.00')
        self.assertEqual(response.data['summary']['available_item_count'], 2)
        self.client.force_authenticate(other)
        url = f"{CART_ITEMS}{first.data['id']}/"
        self.assertEqual(self.client.get(CART, {'user': owner.pk}).data['count'], 0)
        self.assertEqual(self.client.patch(url, {'quantity': 1}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locking')
class ConcurrentCommerceCase(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('09121234567')
        self.other = get_user_model().objects.create_user('09121234568')
        category = Category.objects.create(name='Tables', slug='tables')
        self.product = Product.objects.create(title='Table', slug='table', sku='T-1', category=category,
                                              price=100, stock=1)

    def post_concurrently(self, url, data, users):
        barrier = Barrier(len(users), timeout=10)

        def post(user):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user)
                barrier.wait()
                return client.post(url, data, format='json').status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(users)) as pool:
            return sorted(pool.map(post, users))

class ConcurrentCommerceTests(ConcurrentCommerceCase):
    def test_concurrent_same_account_cart_writes_create_one_line(self):
        responses = self.post_concurrently(CART_ITEMS, {'product_id': self.product.pk, 'quantity': 1},
                                           (self.user, self.user))
        self.assertEqual(responses, [200, 201])
        self.assertEqual(CartItem.objects.get().quantity, 1)
        self.assertEqual(AuditLog.objects.filter(action='cart_add').count(), 1)

    def test_concurrent_carts_do_not_reserve_stock(self):
        responses = self.post_concurrently(CART_ITEMS, {'product_id': self.product.pk, 'quantity': 1},
                                           (self.user, self.other))
        self.assertEqual(responses, [201, 201])
        self.assertEqual(CartItem.objects.count(), 2)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)

    def test_concurrent_addresses_have_one_default(self):
        self.assertEqual(self.post_concurrently(ADDRESSES, {**ADDRESS, 'is_default': True},
                                               (self.user, self.user)), [201, 201])
        self.assertEqual(Address.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

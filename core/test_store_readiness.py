from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core import mail
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from core.models import AuditLog, ContactMessage, NewsletterSubscription
from orders.models import Address, InventoryMovement, Order
from categories.models import Category
from products.models import Product

PREFIX = '/api/v1/'
OLD_PASSWORD = 'Old-Test-Secret-93!'
NEW_PASSWORD = 'New-Password-Change-36!'


def inline(task, *args):
    task.run(*args)


def code():
    return mail.outbox[-1].body.split('Code: ', 1)[1].splitlines()[0]


@override_settings(TRANSACTIONAL_EMAIL_ENABLED=True,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ReadinessAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user('09123456789', OLD_PASSWORD, email='unverified@example.org')
        self.staff = User.objects.create_user('09123456788', OLD_PASSWORD, is_staff=True)
        self.acquire = patch('accounts.recovery.enqueue', side_effect=inline)
        self.outreach = patch('core.store_api.enqueue', side_effect=inline)
        self.acquire.start()
        self.outreach.start()
        self.addCleanup(self.acquire.stop)
        self.addCleanup(self.outreach.stop)

    def post(self, route, data):
        return self.client.post(PREFIX + route, data, format='json')

    def test_verified_recovery_and_single_use_reset(self):
        root = 'auth/password/recovery/'
        self.assertEqual(self.post(root, {'phone': self.user.phone, 'email': self.user.email}).status_code, 202)
        self.assertEqual(len(mail.outbox), 0)
        self.client.force_authenticate(self.user)
        email = 'verified@example.org'
        self.assertEqual(self.post(root + 'email/', {'email': email, 'password': OLD_PASSWORD}).status_code, 202)
        proof = code()
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.post(root + 'email/confirm/', {'token': proof}).status_code, 400)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.post(root + 'email/confirm/', {'token': proof}).status_code, 204)
        self.assertEqual(self.post(root + 'email/confirm/', {'token': proof}).status_code, 400)
        self.client.force_authenticate(None)
        first = self.post('auth/login/', {'phone': self.user.phone, 'password': OLD_PASSWORD}).data
        self.assertEqual(self.post(root, {'phone': self.user.phone, 'email': email}).status_code, 202)
        payload = {'phone': self.user.phone, 'token': code(), 'password': NEW_PASSWORD}
        self.assertEqual(self.post(root + 'confirm/', {**payload, 'password': '123'}).status_code, 400)
        self.assertEqual(self.post(root + 'confirm/', payload).status_code, 204)
        self.assertEqual(self.post(root + 'confirm/', payload).status_code, 400)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + first['access'])
        self.assertEqual(self.client.get(PREFIX + 'auth/me/').status_code, 401)
        self.client.credentials()
        self.assertEqual(self.post('auth/token/refresh/', {'refresh': first['refresh']}).status_code, 401)
        self.assertEqual(self.post('auth/login/', {'phone': self.user.phone, 'password': NEW_PASSWORD}).status_code, 200)

    def test_contact_rejects_invalid_and_saves_for_staff(self):
        root = 'store/contact/'
        self.assertEqual(self.post(root, {'name': 'Test', 'email': 'invalid', 'message': 'Text'}).status_code, 400)
        self.assertEqual(self.post(root, {'name': 'Test', 'email': 'customer@example.org', 'message': 'Message'}).status_code, 201)
        self.assertEqual(ContactMessage.objects.get().message, 'Message')
        self.assertEqual(self.client.get(PREFIX + root).status_code, 405)

    def test_newsletter_confirmation_and_replay(self):
        root = 'store/newsletter/'
        self.assertEqual(self.post(root, {'email': 'Guest@example.org', 'action': 'subscribe'}).status_code, 202)
        self.assertFalse(NewsletterSubscription.objects.get().active)
        old_code = code()
        self.assertEqual(self.post(root + 'confirm/', {'token': old_code}).status_code, 204)
        self.assertTrue(NewsletterSubscription.objects.get().active)
        self.assertEqual(self.post(root, {'email': 'guest@example.org', 'action': 'unsubscribe'}).status_code, 202)
        self.assertEqual(self.post(root + 'confirm/', {'token': code()}).status_code, 204)
        self.assertFalse(NewsletterSubscription.objects.get().active)
        self.assertEqual(self.post(root + 'confirm/', {'token': old_code}).status_code, 400)

    @override_settings(TRANSACTIONAL_EMAIL_ENABLED=False)
    def test_disabled_delivery_is_explicit(self):
        response = self.post('auth/password/recovery/', {'phone': self.user.phone, 'email': self.user.email})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.post('store/newsletter/', {'email': self.user.email, 'action': 'subscribe'}).status_code, 503)

    def test_order_status_stale_request_and_permissions(self):
        order = Order.objects.create(user=self.user, order_number='QA-READINESS', status='paid',
                                     shipping_address_snapshot={'recipient_name': 'Test', 'recipient_phone': self.user.phone,
                                         'province': 'Tehran', 'city': 'Tehran', 'address_line': 'Address',
                                         'postal_code': '1234567890'}, subtotal=10, total_amount=10, currency='IRR')
        endpoint = PREFIX + f'admin/orders/{order.pk}/status/'
        payload = {'expected_status': 'paid', 'status': 'processing'}
        for actor in (self.user, self.staff):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.patch(endpoint, payload, format='json').status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(codename='change_order'))
        self.client.force_authenticate(User.objects.get(pk=self.staff.pk))
        self.assertEqual(self.client.patch(endpoint, {'expected_status': 'paid', 'status': 'completed'}, format='json').status_code, 409)
        self.assertEqual(self.client.patch(endpoint, payload, format='json').status_code, 200)
        self.assertEqual(self.client.patch(endpoint, payload, format='json').status_code, 409)
        self.assertEqual(self.client.patch(endpoint, {'expected_status': 'processing', 'status': 'completed'}, format='json').status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action='order_status_change', actor=self.staff).count(), 2)


    def test_staff_cancel_releases_stock_once(self):
        category = Category.objects.create(name='QA', slug='qa')
        product = Product.objects.create(title='QA', slug='qa', sku='QA', category=category, price=10, stock=2)
        address = Address.objects.create(user=self.user, recipient_name='Test', recipient_phone=self.user.phone,
                                         province='Tehran', city='Tehran', address_line='Address',
                                         postal_code='1234567890')
        self.client.force_authenticate(self.user)
        self.assertEqual(self.post('cart/items/', {'product_id': product.pk, 'quantity': 1}).status_code, 201)
        checkout = self.post('orders/', {'address_id': address.pk})
        self.assertEqual(checkout.status_code, 201)
        order_id = checkout.data['id']
        self.staff.user_permissions.add(Permission.objects.get(codename='change_order'))
        self.client.force_authenticate(self.staff)
        endpoint = PREFIX + f'admin/orders/{order_id}/status/'
        data = {'expected_status': 'pending_payment', 'status': 'cancelled'}
        self.assertEqual(self.client.patch(endpoint, data, format='json').status_code, 200)
        self.assertEqual(self.client.patch(endpoint, data, format='json').status_code, 409)
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)
        self.assertEqual(InventoryMovement.objects.filter(order_id=order_id, actor=self.staff).count(), 1)

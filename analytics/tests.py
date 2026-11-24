from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from core.test_catalog import CatalogTestCase
from .models import ProductView
from .services import GUEST_COOKIE


class AnalyticsTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.metrics_url = f'/api/v1/admin/products/{self.product.pk}/views/'

    def grant_metrics(self, user):
        user.user_permissions.add(Permission.objects.get(codename='view_store_metrics', content_type__app_label='core'))

    def test_guest_view_and_deduplication(self):
        for _ in range(2):
            response = self.client.get(self.path, HTTP_USER_AGENT='Guest browser')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['view_count'], 1)
        self.assertIn(GUEST_COOKIE, self.client.cookies)
        guest_view = ProductView.objects.get(product=self.product)
        self.assertFalse(guest_view.authenticated)
        self.assertEqual(len(guest_view.visitor_key), 64)
        self.assertEqual(self.client.get('/api/v1/products/most-viewed/').data['results'][0]['view_count'], 1)

    def test_authenticated_view_identity_and_deduplication(self):
        person = self.user()
        self.client.force_authenticate(person)
        for _ in range(2):
            response = self.client.get(self.path, HTTP_USER_AGENT='Client changes user agent')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data['view_count'], 1)
        self.assertNotIn(GUEST_COOKIE, self.client.cookies)
        self.assertTrue(ProductView.objects.get(product=self.product).authenticated)

        other_device = APIClient()
        other_device.force_authenticate(person)
        self.assertEqual(other_device.get(self.path, HTTP_USER_AGENT='Another browser').data['view_count'], 1)
        other_device.force_authenticate(self.user(2))
        self.assertEqual(other_device.get(self.path).data['view_count'], 2)
        self.assertEqual(ProductView.objects.filter(product=self.product, authenticated=True).count(), 2)

    def test_repeat_after_expiry_counts_as_view_but_not_new_unique(self):
        self.client.get(self.path)
        event = ProductView.objects.get(product=self.product)
        cache.delete(f'catalog:view:{self.product.pk}:{event.visitor_key}')
        response = self.client.get(self.path)
        self.assertEqual(response.data['view_count'], 2)
        self.assertEqual(ProductView.objects.values('visitor_key').distinct().count(), 1)

    def test_metrics_permissions_and_response_privacy(self):
        self.assertEqual(self.client.get(self.metrics_url).status_code, 401)
        customer = self.user()
        self.grant_metrics(customer)
        self.client.force_authenticate(customer)
        self.client.get(self.path)
        self.assertEqual(self.client.get(self.metrics_url).status_code, 403)
        staff = self.user(2, is_staff=True)
        self.client.force_authenticate(staff)
        self.assertEqual(self.client.get(self.metrics_url).status_code, 403)
        self.grant_metrics(staff)
        self.client.force_authenticate(type(staff).objects.get(pk=staff.pk))
        response = self.client.get(self.metrics_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data),
                         {'total', 'authenticated', 'guest', 'unique', 'daily', 'weekly', 'monthly', 'last_view_at'})
        self.assertEqual(response.data['authenticated'], 1)

    def test_metrics_windows_include_boundary_and_exclude_older_views(self):
        now = timezone.now()
        offsets = [timedelta(hours=1), timedelta(days=1), timedelta(days=1, seconds=1),
                   timedelta(days=7), timedelta(days=7, seconds=1), timedelta(days=30),
                   timedelta(days=30, seconds=1)]
        for i, offset in enumerate(offsets):
            event = ProductView.objects.create(product=self.product, visitor_key=f'visitor-{i // 2}',
                                               authenticated=i % 2 == 0)
            ProductView.objects.filter(pk=event.pk).update(created_at=now - offset)

        admin = self.user(is_staff=True, is_superuser=True)
        self.client.force_authenticate(admin)
        with patch('analytics.services.timezone.now', return_value=now):
            result = self.client.get(self.metrics_url)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(dict(result.data), {
            'total': 7, 'authenticated': 4, 'guest': 3, 'unique': 4, 'daily': 2, 'weekly': 4,
            'monthly': 6, 'last_view_at': (now - offsets[0]).isoformat().replace('+00:00', 'Z'),
        })

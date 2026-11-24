from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command

from accounts.models import User
from core.models import AuditLog
from core.test_catalog import CatalogTestCase


class AdminRoleTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        output = StringIO()
        call_command('provision_roles', stdout=output)

    def assign(self, name, number, **fields):
        account = self.user(number, **fields)
        account.groups.add(Group.objects.get(name=name))
        return account

    def test_role_matrix_and_idempotent_provisioning(self):
        call_command('provision_roles', stdout=StringIO())
        self.assertEqual(set(Group.objects.values_list('name', flat=True)),
                         {'Super Admin', 'Admin', 'Product Manager', 'Order Manager', 'Support Manager'})
        matrix = {
            'Admin': (200, 200, 200, 200, 200),
            'Product Manager': (403, 200, 403, 200, 403),
            'Support Manager': (200, 403, 200, 403, 403),
            'Order Manager': (403, 403, 403, 403, 403),
        }
        paths = ['users', 'products', 'reviews', 'reports/most-viewed-products', 'audit-logs']
        for number, (role, expected) in enumerate(matrix.items(), 1):
            user = self.assign(role, number, is_staff=True)
            self.client.force_authenticate(user)
            for endpoint, status_code in zip(paths, expected):
                with self.subTest(role=role, endpoint=endpoint):
                    self.assertEqual(self.client.get(f'/api/v1/admin/{endpoint}/').status_code, status_code)
        self.client.force_authenticate(self.assign('Admin', 5))
        self.assertEqual(self.client.get('/api/v1/admin/users/').status_code, 403)
        root = self.assign('Super Admin', 6, is_staff=True, is_superuser=True)
        self.client.force_authenticate(root)
        self.assertEqual(self.client.get('/api/v1/admin/audit-logs/').status_code, 200)

    def test_customer_management_deactivates_and_revokes_sessions(self):
        password = 'Strong!AuditedPass6'
        customer = User.objects.create_user('09121234561', password, first_name='Customer')
        protected = self.assign('Product Manager', 2)
        login = {'phone': customer.phone, 'password': password}
        initial = self.client.post('/api/v1/auth/login/', login).data
        admin = self.assign('Admin', 3, is_staff=True)
        self.client.force_authenticate(admin)
        result = self.client.get('/api/v1/admin/users/', {'search': 'customer'})
        self.assertEqual([row['id'] for row in result.data['results']], [customer.pk])
        self.assertIn('no-store', result['Cache-Control'])
        self.assertEqual(self.client.patch(f'/api/v1/admin/users/{protected.pk}/', {'is_active': False}).status_code, 404)
        url = f'/api/v1/admin/users/{customer.pk}/'
        self.assertEqual(self.client.patch(url, {}, format='multipart').status_code, 400)
        result = self.client.patch(url, {'is_active': False, 'is_staff': True, 'phone': protected.phone}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(result.data['is_active'])
        self.assertEqual(result.data['phone'], customer.phone)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post('/api/v1/auth/login/', login).status_code, 401)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.patch(url, {'is_active': True}, format='json').status_code, 200)
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {initial['access']}")
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post('/api/v1/auth/token/refresh/', {'refresh': initial['refresh']}).status_code, 401)
        latest = self.client.post('/api/v1/auth/login/', login)
        self.assertEqual(latest.status_code, 200, latest.data)
        refreshed = self.client.post('/api/v1/auth/token/refresh/', {'refresh': latest.data['refresh']})
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}")
        self.assertEqual(self.client.get('/api/v1/auth/me/').status_code, 200)
        self.assertEqual(list(AuditLog.objects.filter(actor=admin).order_by('pk').values_list('action', flat=True)),
                         ['deactivate', 'activate'])

    def test_recommendation_settings_and_admin_reports(self):
        self.client.force_authenticate(self.assign('Admin', 1, is_staff=True))
        settings = '/api/v1/admin/recommendation-settings/'
        self.assertEqual(self.client.get(settings).data['history_days'], 30)
        self.assertEqual(self.client.patch(settings, {'seed_limit': 1}).status_code, 400)
        result = self.client.patch(settings, {'history_days': 10, 'seed_limit': 2, 'min_viewed_products': 1})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.client.get(settings).data['history_days'], 10)
        self.assertTrue(AuditLog.objects.filter(model_label='recommendations.recommendationpolicy').exists())
        popularity = self.client.get('/api/v1/admin/ranking-weights/').data['results'][0]
        response = self.client.patch(f"/api/v1/admin/ranking-weights/{popularity['id']}/", {'views': 40})
        self.assertEqual(response.data['views'], 40)
        self.assertEqual(self.client.get('/api/v1/admin/reports/popular-categories/').data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/admin/reports/popular-products/').data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/admin/reports/most-viewed-products/').data['count'], 1)

    def test_catalog_weighted_ranking_uses_configured_weights(self):
        from products.models import Product

        item = Product.objects.create(title='Featured', slug='featured-item', sku='F-1',
                                      price=100, category=self.category, is_featured=True)
        self.client.force_authenticate(self.assign('Admin', 1, is_staff=True))
        weights = self.client.get('/api/v1/admin/ranking-weights/').data['results'][0]
        response = self.client.patch(f"/api/v1/admin/ranking-weights/{weights['id']}/",
                                     {'featured': 100, 'discount': 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/products/', {'ordering': '-score'}).data['results'][0]['id'],
                         item.pk)

from core.test_catalog import CatalogTestCase
from .models import Category


class CategoryTests(CatalogTestCase):
    def test_children_and_disabled_ancestor(self):
        Category.objects.create(name='میز جلو مبلی', slug='coffee-table', parent=self.category)
        result = self.client.get(f'/api/v1/categories/{self.root.slug}/children/')
        self.assertEqual([category['slug'] for category in result.data['results']], [self.category.slug])
        self.root.is_active = False
        self.root.save(update_fields=['is_active'])
        self.assertEqual(self.client.get('/api/v1/categories/').data['count'], 0)
        self.assertEqual(self.client.get(self.path).status_code, 404)

    def test_admin_can_build_hierarchy_but_cannot_create_cycle(self):
        self.client.force_authenticate(self.user(is_staff=True, is_superuser=True))
        response = self.client.post('/api/v1/admin/categories/',
                                    {'name': 'صندلی', 'slug': 'صندلی', 'parent': self.category.pk})
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.patch(f'/api/v1/admin/categories/{self.root.pk}/', {'parent': response.data['id']})
        self.assertEqual(response.status_code, 400, response.data)
        self.root.refresh_from_db()
        self.assertIsNone(self.root.parent)

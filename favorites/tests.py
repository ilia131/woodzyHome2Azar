from core.test_catalog import CatalogTestCase
from .models import Favorite


class FavoriteTests(CatalogTestCase):
    def test_favorites_are_unique_and_owned(self):
        url = f'/api/v1/favorites/{self.product.pk}/'
        self.assertEqual(self.client.post(url).status_code, 401)
        first = self.user()
        self.client.force_authenticate(first)
        self.assertEqual(self.client.post(url).status_code, 201)
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/favorites/').data['count'], 1)
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.client.get('/api/v1/favorites/').data['count'], 0)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(Favorite.objects.filter(user=first).count(), 1)
        self.assertEqual(self.client.get(self.path).data['favorite_count'], 1)
        self.assertEqual(self.client.get('/api/v1/products/most-favorited/').data['results'][0]['id'], self.product.pk)

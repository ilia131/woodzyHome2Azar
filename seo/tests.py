from urllib.parse import quote

from core.test_catalog import CatalogTestCase
from .models import ProductSEO


class SEOTests(CatalogTestCase):
    def test_fallback_canonical_and_offer_availability(self):
        metadata = self.client.get(self.path).data['seo']
        self.assertEqual(metadata['meta_title'], self.product.title)
        self.assertEqual(metadata['meta_description'], self.product.short_description)
        canonical = f'https://store.example/products/{quote(self.product.slug)}/'
        self.assertEqual(metadata['canonical_url'], canonical)
        self.assertEqual(metadata['open_graph']['url'], canonical)
        structured = metadata['structured_data']
        self.assertEqual(structured['@type'], 'Product')
        self.assertEqual(structured['offers']['@type'], 'Offer')
        self.assertEqual(structured['offers']['price'], '80.00')
        self.assertTrue(structured['offers']['availability'].endswith('/InStock'))
        self.product.stock = 0
        self.product.save(update_fields=['stock'])
        response = self.client.get(self.path)
        self.assertTrue(response.data['seo']['structured_data']['offers']['availability'].endswith('/OutOfStock'))
        self.assertContains(self.client.get('/sitemap.xml'), canonical)
        self.assertContains(self.client.get('/robots.txt'), 'https://store.example/sitemap.xml')
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(self.path).status_code, 404)
        self.assertNotContains(self.client.get('/sitemap.xml'), canonical)

    def test_explicit_metadata_and_noindex(self):
        self.client.force_authenticate(self.user(is_staff=True, is_superuser=True))
        url = '/api/v1/admin/seo/'
        payload = {'product': self.product.pk, 'meta_title': 'Custom title', 'meta_description': 'Custom description',
                   'canonical_url': 'https://store.example/custom/', 'og_title': 'Social title',
                   'structured_data': {'brand': {'@type': 'Brand', 'name': 'HomeAksoria'}},
                   'robots_index': False}
        result = self.client.post(url, payload, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        metadata = self.client.get(self.path).data['seo']
        self.assertEqual(metadata['meta_title'], payload['meta_title'])
        self.assertEqual(metadata['meta_description'], payload['meta_description'])
        self.assertEqual(metadata['open_graph']['title'], payload['og_title'])
        self.assertEqual(metadata['canonical_url'], payload['canonical_url'])
        self.assertEqual(metadata['structured_data']['brand']['name'], 'HomeAksoria')
        self.assertFalse(metadata['robots_index'])
        self.assertNotContains(self.client.get('/sitemap.xml'), '<loc>')

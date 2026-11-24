from datetime import timedelta
from unittest import skipUnless

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from analytics.models import ProductView
from analytics.services import account_visitor_key
from categories.models import Category
from core.test_catalog import CatalogTestCase
from favorites.models import Favorite
from products.models import Product
from .models import RankingWeights


class RecommendationTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.chairs = Category.objects.create(name='Chairs', slug='chairs', parent=self.root)
        self.decor = Category.objects.create(name='Decor', slug='decor')
        self.chair = self.make_product('Chair', 'chair', self.chairs)
        self.chair_peer = self.make_product('Stool', 'stool', self.chairs, stock=0)
        self.vase = self.make_product('Vase', 'vase', self.decor)

    def make_product(self, title, slug, category, *, stock=2, description='Example', active=True):
        return Product.objects.create(title=title, slug=slug, sku=slug, category=category, stock=stock,
                                      price=100, short_description='', description=description, is_active=active)

    def ids(self, path, **query):
        response = self.client.get(f'/api/v1/{path}/', query)
        self.assertEqual(response.status_code, 200, response.data)
        return [row['id'] for row in response.data['results']]

    def test_guest_and_cold_start_receive_popular_products(self):
        first = self.user()
        Favorite.objects.create(user=first, product=self.chair_peer)
        popular = self.ids('products/popular')
        self.assertEqual(popular[0], self.chair_peer.pk)
        self.assertEqual(self.ids('products/recommended'), popular)
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.ids('products/recommended'), popular)
        self.assertEqual(self.ids('products/recommended', page_size=1, page=2), [popular[1]])

    def test_popularity_settings_and_category_suggestions(self):
        Favorite.objects.create(user=self.user(), product=self.chair)
        for i in range(3):
            ProductView.objects.create(product=self.vase, visitor_key=f'guest-{i}', authenticated=False)
        self.assertEqual(self.ids('products/popular')[0], self.chair.pk)
        self.assertEqual(self.ids('categories/suggested')[0], self.chairs.pk)
        RankingWeights.objects.create(views=10, favorites=1)
        self.assertEqual(self.ids('products/popular')[0], self.vase.pk)
        self.assertEqual(self.ids('categories/suggested')[0], self.decor.pk)

    def test_favorites_personalize_results_and_are_private(self):
        url = 'recommendations/from-favorites'
        self.assertEqual(self.client.get(f'/api/v1/{url}/').status_code, 401)
        first, second = self.user(), self.user(2)
        Favorite.objects.create(user=first, product=self.chair)
        Favorite.objects.create(user=second, product=self.vase)
        self.client.force_authenticate(first)
        self.assertEqual(self.ids(url, user=second.pk), [self.chair_peer.pk])
        self.assertEqual(self.ids('products/recommended')[0], self.chair_peer.pk)
        self.assertEqual(self.ids('categories/suggested')[0], self.chairs.pk)
        response = self.client.get('/api/v1/products/recommended/')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotIn(self.chair.pk, [row['id'] for row in response.data['results']])
        self.client.force_authenticate(second)
        self.assertEqual(self.ids(url, user=first.pk), [])

    def test_recent_distinct_own_views_personalize_and_old_views_do_not_count(self):
        account, other = self.user(), self.user(2)
        self.client.get(f'/api/v1/products/{self.vase.slug}/')
        self.client.force_authenticate(other)
        self.client.get(f'/api/v1/products/{self.vase.slug}/')
        self.client.get(self.path)
        self.client.force_authenticate(account)
        self.client.get(f'/api/v1/products/{self.chair.slug}/')
        old = ProductView.objects.create(product=self.product, visitor_key=account_visitor_key(account.pk),
                                         authenticated=True)
        ProductView.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
        ProductView.objects.create(product=self.chair, visitor_key=account_visitor_key(account.pk), authenticated=True)
        self.assertEqual(self.ids('products/recommended'), self.ids('products/popular'))
        self.client.get(self.path)
        results = self.ids('products/recommended')
        self.assertEqual(results[0], self.chair_peer.pk)
        self.assertNotIn(self.chair.pk, results)
        self.assertNotIn(self.product.pk, results)
        self.assertIn(self.vase.pk, results)

    @override_settings(RECOMMENDATION_OPTIONS={'min_viewed_products': 1})
    def test_view_threshold_can_be_configured(self):
        self.client.force_authenticate(self.user())
        self.client.get(f'/api/v1/products/{self.chair.slug}/')
        self.assertEqual(self.ids('products/recommended')[0], self.chair_peer.pk)

    def test_similar_products_and_new_related_products_keep_out_of_stock_items(self):
        same = self.make_product('Armchair', 'armchair', self.chairs)
        cousin = self.make_product('Desk', 'desk', self.category)
        similar = self.ids('products/chair/similar')
        self.assertIn(self.chair_peer.pk, similar)
        self.assertLess(similar.index(same.pk), similar.index(cousin.pk))
        self.assertNotIn(self.chair.pk, similar)
        self.assertEqual(self.ids('products/chair/related')[0], cousin.pk)

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL trigram search is required')
    def test_content_similarity_can_cross_categories(self):
        source = self.make_product('Lamp', 'lamp', self.decor, description='hand painted copper wall fitting')
        match = self.make_product('Sconce', 'sconce', self.chairs,
                                  description='hand painted copper wall fitting')
        self.assertIn(match.pk, self.ids(f'products/{source.slug}/similar'))

    def test_hidden_products_branches_and_seeds_are_excluded(self):
        disabled = Category.objects.create(name='Hidden branch', slug='hidden', is_active=False)
        child = Category.objects.create(name='Hidden child', slug='hidden-child', parent=disabled)
        hidden_child = self.make_product('Chair', 'hidden-child-chair', child)
        hidden_product = self.make_product('Chair', 'inactive-chair', self.chairs, active=False)
        account = self.user()
        self.client.force_authenticate(account)
        Favorite.objects.create(user=account, product=hidden_child)
        for path in ('products/popular', 'products/recommended', 'products/chair/similar',
                     'products/chair/related', 'recommendations/from-favorites'):
            with self.subTest(path=path):
                self.assertTrue({hidden_child.pk, hidden_product.pk}.isdisjoint(self.ids(path)))
        self.assertNotIn(child.pk, self.ids('categories/suggested'))
        for slug in (hidden_child.slug, hidden_product.slug):
            self.assertEqual(self.client.get(f'/api/v1/products/{slug}/similar/').status_code, 404)
            self.assertEqual(self.client.get(f'/api/v1/products/{slug}/related/').status_code, 404)

    def test_product_feed_query_count_does_not_grow_with_page_size(self):
        url = '/api/v1/products/popular/'
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self.client.get(url, {'page_size': 1}).status_code, 200)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self.client.get(url, {'page_size': 20}).status_code, 200)
        self.assertEqual(len(one), len(many))

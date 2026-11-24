from unittest import skipUnless

from django.db import connection

from categories.models import Category
from core.test_catalog import CatalogTestCase
from products.models import Product
from .models import RecentSearch, SearchTerm


class SearchTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.console = self.make_product('Cedar Console', 'cedar-console', 'Natural wood for a narrow hallway',
                                         price=140, stock=0)
        self.armchair = self.make_product('صندلی تک‌نفره', 'armchair', 'روکش کرم', price=160)

    def make_product(self, title, slug, description, *, price=75, stock=2, category=None, active=True):
        return Product.objects.create(
            title=title, slug=slug, sku=slug, price=price, stock=stock, short_description='Catalog item',
            description=description, category=category or self.category, is_active=active,
        )

    def search(self, term, **params):
        return self.client.get('/api/v1/search/products/', {'q': term, **params})

    def get_ids(self, response):
        self.assertEqual(response.status_code, 200, response.data)
        return [row['id'] for row in response.data['results']]

    def test_persian_arabic_characters_zwnj_and_spaces(self):
        variants = ['صندلي   تك نفره', 'صندلی تک‌نفره', ' صندلی   تک نفره ']
        for term in variants:
            with self.subTest(term=term):
                self.assertEqual(self.get_ids(self.search(term))[0], self.armchair.pk)
        self.assertEqual(SearchTerm.objects.get(term='صندلی تک نفره').count, 3)
        self.assertFalse(RecentSearch.objects.exists())

    def test_english_search_and_category_name(self):
        self.assertEqual(self.get_ids(self.search('CEDAR'))[0], self.console.pk)
        decor = Category.objects.create(name='Decor Accessories', slug='decor')
        vase = self.make_product('Vase', 'vase', 'Clay', category=decor)
        self.assertEqual(self.get_ids(self.search('decor accessories')), [vase.pk])

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL full text search is required')
    def test_full_text_matches_non_adjacent_description_words(self):
        self.assertEqual(self.get_ids(self.search('hallway natural')), [self.console.pk])

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL trigram search is required')
    def test_trigram_returns_approximate_product_and_category_matches(self):
        self.assertIn(self.console.pk, self.get_ids(self.search('cedarr')))
        self.assertIn(self.armchair.pk, self.get_ids(self.search('صندلیی')))
        decor = Category.objects.create(name='Decor Accessories', slug='decor')
        response = self.client.get('/api/v1/search/suggestions/', {'q': 'accessoriess'})
        self.assertIn(decor.pk, [row['id'] for row in response.data['categories']])

    def test_autocomplete_matches_titles_and_categories_without_recording(self):
        self.client.force_authenticate(self.user())
        url = '/api/v1/search/suggestions/'
        response = self.client.get(url, {'q': 'مي', 'limit': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['products'][0]['id'], self.product.pk)
        self.assertEqual(response.data['categories'][0]['id'], self.category.pk)
        self.assertEqual(len(response.data['products']), 1)
        self.assertFalse(SearchTerm.objects.exists())
        self.assertFalse(RecentSearch.objects.exists())

    def test_paginated_filters_and_ordering(self):
        response = self.search('میز', category=self.root.slug, in_stock='true', min_price=60, max_price=180,
                               ordering='price', page_size=1)
        self.assertEqual(self.get_ids(response), [self.product.pk])
        self.assertEqual(response.data['count'], 2)
        response = self.search('میز', category=self.root.slug, in_stock='true', min_price=60, max_price=180,
                               ordering='price', page_size=1, page=2)
        self.assertEqual(self.get_ids(response), [self.armchair.pk])
        self.assertEqual(SearchTerm.objects.get(term='میز').count, 1)

    def test_popular_terms_guest_order_and_catalog_visibility(self):
        for term in ('cedar', 'cedar', 'میز'):
            self.assertEqual(self.search(term).status_code, 200)
        self.search('natural wood')
        self.search('private search phrase')
        url = '/api/v1/search/popular/'
        page = self.client.get(url, {'page_size': 1})
        self.assertEqual(page.data['count'], 2)
        self.assertEqual(page.data['results'][0], {'term': 'cedar', 'count': 2})
        self.console.is_active = False
        self.console.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(url).data['results'], [{'term': 'میز', 'count': 1}])
        self.root.is_active = False
        self.root.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(url).data['count'], 0)

    def test_recent_searches_are_private_and_sorted_by_latest_submission(self):
        url = '/api/v1/search/recent/'
        self.assertEqual(self.client.get(url).status_code, 401)
        first, second = self.user(), self.user(2)
        self.client.force_authenticate(first)
        for term in ('cedar', 'no results phrase', 'CEDAR'):
            self.assertEqual(self.search(term).status_code, 200)
        response = self.client.get(url, {'user': second.pk})
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual([row['term'] for row in response.data['results']], ['cedar', 'no results phrase'])
        self.assertEqual(SearchTerm.objects.get(term='no results phrase').count, 0)
        self.client.force_authenticate(second)
        self.search('میز')
        self.assertEqual([row['term'] for row in self.client.get(url, {'user': first.pk}).data['results']], ['میز'])

    def test_inactive_products_and_category_descendants_never_match(self):
        self.make_product('Hidden catalog item', 'hidden', 'hidden', active=False)
        disabled = Category.objects.create(name='Hidden furniture', slug='hidden-furniture', is_active=False)
        child = Category.objects.create(name='Hidden decor', slug='hidden-child', parent=disabled)
        self.make_product('Hidden vase', 'hidden-vase', 'hidden', category=child)
        self.assertEqual(self.get_ids(self.search('hidden')), [])
        self.assertEqual(self.get_ids(self.search('hidden', category=child.slug)), [])
        result = self.client.get('/api/v1/search/suggestions/', {'q': 'hidden'})
        self.assertEqual(result.data, {'products': [], 'categories': []})

    def test_invalid_search_parameters_do_not_create_history(self):
        self.client.force_authenticate(self.user())
        for term in ('', '‌  ', 'م', '!!!', 'a' * 121):
            with self.subTest(term=term):
                self.assertEqual(self.search(term).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/search/suggestions/', {'q': 'میز', 'limit': 21}).status_code, 400)
        self.assertFalse(SearchTerm.objects.exists())

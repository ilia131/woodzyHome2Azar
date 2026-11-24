from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from analytics.models import ProductView
from analytics.services import account_visitor_key
from core.test_catalog import CatalogTestCase
from favorites.models import Favorite
from notifications.models import Notification
from products.models import Product
from reviews.models import Review, ReviewReply
from search.models import RecentSearch


class DashboardTests(CatalogTestCase):
    list_routes = ('favorites', 'reviews', 'searches', 'views', 'notifications')

    def get_dashboard(self, route, **params):
        return self.client.get(f'/api/v1/dashboard/{route}/', params)

    def make_product(self, slug, *, active=True):
        return Product.objects.create(title=slug, slug=slug, sku=slug, category=self.category, price=100,
                                      is_active=active)

    def add_review(self, user, product, rating, *, approved=False, moderated_at=None):
        return Review.objects.create(user=user, product=product, rating=rating, title='My review',
                                     comment='Review text.', is_approved=approved, moderated_at=moderated_at)

    def add_notification(self, user, title, *, read=False):
        return Notification.objects.create(user=user, title=title, body='Message',
                                           read_at=timezone.now() if read else None)

    def test_all_routes_reject_guests_and_disable_caching(self):
        for route in ('overview', *self.list_routes):
            with self.subTest(route=route):
                response = self.get_dashboard(route)
                self.assertEqual(response.status_code, 401)
                self.assertIn('no-store', response['Cache-Control'])

    def test_empty_account_overview_and_lists_use_real_empty_states(self):
        account = self.user(first_name='First', email='first@example.test')
        token = RefreshToken.for_user(account).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.get_dashboard('overview')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profile']['id'], account.pk)
        self.assertEqual(response.data['profile']['email'], account.email)
        self.assertNotIn('password', response.data['profile'])
        self.assertEqual(set(response.data), {'profile', 'favorite_count', 'reviews', 'notifications'})
        self.assertEqual(response.data['favorite_count'], 0)
        self.assertEqual(response.data['reviews'], {'count': 0, 'average_rating': None})
        self.assertEqual(response.data['notifications'], {'count': 0, 'unread_count': 0})
        for route in self.list_routes:
            with self.subTest(route=route):
                response = self.get_dashboard(route)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data, {'count': 0, 'next': None, 'previous': None, 'results': []})
                self.assertIn('no-store', response['Cache-Control'])

    def test_overview_totals_count_all_own_records_and_ignore_other_users(self):
        owner, other = self.user(first_name='Mine'), self.user(2, first_name='Other')
        hidden = self.make_product('inactive', active=False)
        for product in (self.product, hidden):
            Favorite.objects.create(user=owner, product=product)
        Favorite.objects.create(user=other, product=self.product)
        self.add_review(owner, self.product, 5, approved=True)
        self.add_review(owner, hidden, 2, moderated_at=timezone.now())
        self.add_review(other, self.product, 1, approved=True)
        self.add_notification(owner, 'Read', read=True)
        self.add_notification(owner, 'Unread')
        self.add_notification(other, 'Private')
        self.client.force_authenticate(owner)
        response = self.get_dashboard('overview', user=other.pk, user_id=other.pk)
        self.assertEqual(response.data['profile']['id'], owner.pk)
        self.assertEqual(response.data['favorite_count'], 2)
        self.assertEqual(response.data['reviews'], {'count': 2, 'average_rating': 3.5})
        self.assertEqual(response.data['notifications'], {'count': 2, 'unread_count': 1})
        favorites = self.get_dashboard('favorites', user=other.pk)
        self.assertEqual([item['id'] for item in favorites.data['results']], [self.product.pk])

    def test_reviews_show_own_moderation_states_and_prefetch_replies(self):
        owner, other = self.user(), self.user(2)
        pending = self.add_review(owner, self.product, 3)
        rejected = self.add_review(owner, self.make_product('rejected'), 2, moderated_at=timezone.now())
        approved = self.add_review(owner, self.make_product('approved'), 5, approved=True)
        self.add_review(other, self.product, 4, approved=True)
        ReviewReply.objects.create(review=approved, author=other, comment='Staff response')
        self.client.force_authenticate(owner)
        with CaptureQueriesContext(connection) as small:
            first = self.get_dashboard('reviews', user=other.pk, page_size=1)
        with CaptureQueriesContext(connection) as large:
            response = self.get_dashboard('reviews', user=other.pk, page_size=10)
        self.assertEqual(len(small), len(large))
        self.assertEqual(first.data['results'][0]['id'], approved.pk)
        results = response.data['results']
        self.assertEqual([row['id'] for row in results], [approved.pk, rejected.pk, pending.pk])
        self.assertEqual([row['is_approved'] for row in results], [True, False, False])
        self.assertIsNotNone(results[1]['moderated_at'])
        self.assertIsNone(results[2]['moderated_at'])
        self.assertEqual(results[0]['replies'][0]['comment'], 'Staff response')
        self.assertNotIn('author', results[0]['replies'][0])

    def test_recent_searches_reuse_private_recorded_search_history(self):
        owner, other = self.user(), self.user(2)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get('/api/v1/search/products/', {'q': 'Other private phrase'}).status_code, 200)
        self.client.force_authenticate(owner)
        for phrase in ('ميز', 'Another phrase', 'میز'):
            self.assertEqual(self.client.get('/api/v1/search/products/', {'q': phrase}).status_code, 200)
        self.assertEqual(RecentSearch.objects.filter(user=owner).count(), 2)
        response = self.get_dashboard('searches', page_size=1, user=other.pk)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['term'], 'میز')
        self.assertTrue(response.data['next'])
        response = self.get_dashboard('searches', page_size=1, page=2)
        self.assertEqual(response.data['results'][0]['term'], 'another phrase')

    def test_view_history_excludes_guests_other_accounts_and_hidden_products(self):
        owner, other = self.user(), self.user(2)
        other_product = self.make_product('other-product')
        own_second = self.make_product('own-second')
        hidden = self.make_product('hidden', active=False)
        self.client.get(f'/api/v1/products/{other_product.slug}/')
        self.client.force_authenticate(other)
        self.client.get(f'/api/v1/products/{other_product.slug}/')
        self.client.force_authenticate(owner)
        self.client.get(self.path)
        self.client.get(self.path)
        self.client.get(f'/api/v1/products/{own_second.slug}/')
        ProductView.objects.create(product=hidden, visitor_key=account_visitor_key(owner.pk), authenticated=True)
        response = self.get_dashboard('views', user=other.pk, page_size=1)
        self.assertEqual(response.data['count'], 2)
        item = response.data['results'][0]
        self.assertEqual(item['product']['id'], own_second.pk)
        self.assertEqual(set(item), {'id', 'viewed_at', 'product'})
        second = self.get_dashboard('views', page_size=1, page=2)
        self.assertEqual(second.data['results'][0]['product']['id'], self.product.pk)
        self.root.is_active = False
        self.root.save(update_fields=['is_active'])
        self.assertEqual(self.get_dashboard('views').data['count'], 0)

    def test_notifications_are_private_paginated_and_report_read_state(self):
        owner, other = self.user(), self.user(2)
        older = self.add_notification(owner, 'Read message', read=True)
        latest = self.add_notification(owner, 'Unread message')
        self.add_notification(other, 'Other private message')
        self.client.force_authenticate(owner)
        response = self.get_dashboard('notifications', page_size=1, user=other.pk)
        self.assertEqual(response.data['count'], 2)
        item = response.data['results'][0]
        self.assertEqual(item['id'], latest.pk)
        self.assertFalse(item['is_read'])
        self.assertIsNone(item['read_at'])
        item = self.get_dashboard('notifications', page_size=1, page=2).data['results'][0]
        self.assertEqual(item['id'], older.pk)
        self.assertTrue(item['is_read'])
        self.assertIsNotNone(item['read_at'])
        latest.refresh_from_db()
        self.assertIsNone(latest.read_at)

    def test_favorites_paginate_in_save_order(self):
        owner, other = self.user(), self.user(2)
        latest = self.make_product('new-favorite')
        Favorite.objects.create(user=owner, product=self.product)
        Favorite.objects.create(user=owner, product=latest)
        Favorite.objects.create(user=other, product=self.make_product('other-favorite'))
        self.client.force_authenticate(owner)
        response = self.get_dashboard('favorites', page_size=1, user=other.pk)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['id'], latest.pk)
        response = self.get_dashboard('favorites', page_size=1, page=2)
        self.assertEqual(response.data['results'][0]['id'], self.product.pk)

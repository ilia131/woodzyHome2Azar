from django.contrib.auth.models import Permission
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import AuditLog
from core.test_catalog import CatalogTestCase
from .models import Review, ReviewReply


class ReviewTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.url = f'/api/v1/products/{self.product.pk}/reviews/'
        self.payload = {'rating': 4, 'title': 'کیفیت خوب', 'comment': 'ساخت و بسته‌بندی مناسب بود.'}

    def make_review(self, user, *, rating=4, approved=False):
        return Review.objects.create(product=self.product, user=user, rating=rating, title='Title',
                                     comment='A useful product review.', is_approved=approved)

    def staff(self, number=5, *permissions):
        account = self.user(number, is_staff=True)
        account.user_permissions.add(*Permission.objects.filter(content_type__app_label='reviews',
                                                                 codename__in=permissions))
        return account

    def owner_url(self, review):
        return f'/api/v1/reviews/{review.pk}/'

    def admin_url(self, review):
        return f'/api/v1/admin/reviews/{review.pk}/'

    def test_authenticated_create_pending_and_guest_denied(self):
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 401)
        user = self.user()
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        result = self.client.post(self.url, {**self.payload, 'is_approved': True, 'user': 999}, format='json')
        self.assertEqual(result.status_code, 201, result.data)
        review = Review.objects.get()
        self.assertEqual(review.user, user)
        self.assertEqual(review.title, self.payload['title'])
        self.assertFalse(result.data['is_approved'])
        self.assertIsNone(result.data['moderated_at'])
        self.assertTrue(result.data['created_at'])
        self.assertTrue(result.data['updated_at'])
        self.assertEqual(self.client.get(self.url).data['count'], 0)

    def test_invalid_ratings_and_blank_content_are_rejected(self):
        self.client.force_authenticate(self.user())
        for rating in (0, 6, 2.5, 'bad'):
            with self.subTest(rating=rating):
                self.assertEqual(self.client.post(self.url, {**self.payload, 'rating': rating}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {**self.payload, 'comment': '  '}).status_code, 400)
        self.assertFalse(Review.objects.exists())

    def test_duplicate_policy_applies_before_moderation_and_at_database(self):
        author = self.user()
        self.client.force_authenticate(author)
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 201)
        self.assertEqual(self.client.post(self.url, {**self.payload, 'rating': 5}).status_code, 409)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_review(author)
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 201)
        self.assertEqual(Review.objects.count(), 2)

    def test_owner_edit_reopens_moderation_and_owner_can_delete(self):
        author = self.user()
        review = self.make_review(author, approved=True)
        self.client.force_authenticate(author)
        result = self.client.patch(self.owner_url(review), {'rating': 4}, format='json')
        self.assertTrue(result.data['is_approved'])
        result = self.client.patch(self.owner_url(review), {'rating': 5, 'is_approved': True}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(result.data['is_approved'])
        self.assertEqual(result.data['rating'], 5)
        self.assertIsNone(result.data['moderated_at'])
        self.assertEqual(self.client.get(self.url).data['count'], 0)
        review.refresh_from_db()
        self.assertGreater(review.updated_at, review.created_at)
        self.assertEqual(self.client.delete(self.owner_url(review)).status_code, 204)
        self.assertFalse(Review.objects.exists())
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 201)

    def test_owner_actions_do_not_expose_other_users_reviews(self):
        review = self.make_review(self.user(), approved=True)
        reply = ReviewReply.objects.create(review=review, author=self.staff(), comment='Thanks')
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.client.patch(self.owner_url(review), {'rating': 2}).status_code, 404)
        self.assertEqual(self.client.delete(self.owner_url(review)).status_code, 404)
        self.assertTrue(Review.objects.filter(pk=review.pk).exists())
        public = self.client.get(self.url).data['results'][0]
        self.assertNotIn('user', public)
        self.assertNotIn('is_approved', public)
        self.assertEqual(public['replies'][0]['id'], reply.pk)
        self.assertNotIn('author', public['replies'][0])

    def test_moderation_and_approved_only_product_statistics(self):
        pending = self.make_review(self.user(), rating=5)
        self.make_review(self.user(2), rating=1, approved=True)
        self.client.force_authenticate(self.staff(5, 'view_review', 'change_review'))
        self.assertEqual(self.client.get('/api/v1/admin/reviews/', {'is_approved': 'false',
                                                                   'product': self.product.pk}).data['count'], 1)
        response = self.client.patch(self.admin_url(pending), {'is_approved': True}, format='json')
        self.assertTrue(response.data['is_approved'])
        self.assertTrue(response.data['moderated_at'])
        product = self.client.get(self.path).data
        self.assertEqual(product['review_count'], 2)
        self.assertEqual(product['average_rating'], 3.0)
        response = self.client.patch(self.admin_url(pending), {'is_approved': False}, format='json')
        self.assertFalse(response.data['is_approved'])
        self.assertTrue(response.data['moderated_at'])
        self.assertEqual(self.client.get(self.url).data['count'], 1)
        product = self.client.get(self.path).data
        self.assertEqual(product['review_count'], 1)
        self.assertEqual(product['average_rating'], 1.0)
        self.assertEqual(list(AuditLog.objects.order_by('pk').values_list('action', flat=True)), ['approve', 'reject'])

    def test_moderation_requires_explicit_decision_for_json_and_form(self):
        review = self.make_review(self.user(), approved=True)
        self.client.force_authenticate(self.staff(5, 'change_review'))
        for format_name in ('json', 'multipart'):
            response = self.client.patch(self.admin_url(review), {}, format=format_name)
            self.assertEqual(response.status_code, 400, response.data)
        review.refresh_from_db()
        self.assertTrue(review.is_approved)
        self.assertFalse(AuditLog.objects.exists())

    def test_staff_permissions_and_reply_is_visible_only_after_approval(self):
        review = self.make_review(self.user())
        url = f'{self.admin_url(review)}replies/'
        self.assertEqual(self.client.post(url, {'comment': 'Thanks'}).status_code, 401)
        self.client.force_authenticate(self.staff(3, 'view_review'))
        self.assertEqual(self.client.get(self.admin_url(review)).status_code, 200)
        self.assertEqual(self.client.patch(self.admin_url(review), {'is_approved': True}).status_code, 403)
        self.assertEqual(self.client.post(url, {'comment': 'Thanks'}).status_code, 403)
        self.client.force_authenticate(self.staff(4, 'change_review', 'add_reviewreply'))
        response = self.client.post(url, {'comment': 'Thanks', 'parent': 999, 'author': 999})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['parent'])
        self.assertEqual(self.client.get(self.url).data['count'], 0)
        self.assertEqual(self.client.patch(self.admin_url(review), {'is_approved': True}).status_code, 200)
        self.assertEqual(self.client.get(self.url).data['results'][0]['replies'][0]['comment'], 'Thanks')
        self.assertEqual(AuditLog.objects.filter(model_label='reviews.reviewreply', action='reply').count(), 1)

    def test_review_filters_pagination_and_prefetch(self):
        high = self.make_review(self.user(), rating=5, approved=True)
        low = self.make_review(self.user(2), rating=2, approved=True)
        for review in (high, low):
            ReviewReply.objects.create(review=review, comment='Reply')
        with CaptureQueriesContext(connection) as one:
            result = self.client.get(self.url, {'ordering': 'rating', 'page_size': 1})
        self.assertEqual(result.data['count'], 2)
        self.assertEqual(result.data['results'][0]['id'], low.pk)
        self.assertTrue(result.data['next'])
        with CaptureQueriesContext(connection) as many:
            result = self.client.get(self.url, {'ordering': 'rating', 'page_size': 2})
        self.assertEqual(len(one), len(many))
        self.assertEqual([item['id'] for item in result.data['results']], [low.pk, high.pk])
        self.assertEqual(self.client.get(self.url, {'rating': 5}).data['count'], 1)

    def test_inactive_product_or_ancestor_blocks_public_list_and_submission(self):
        self.client.force_authenticate(self.user())
        for target in (self.product, self.root):
            target.is_active = False
            target.save(update_fields=['is_active'])
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url, self.payload).status_code, 404)
            target.is_active = True
            target.save(update_fields=['is_active'])

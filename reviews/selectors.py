from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from products.selectors import visible_products
from .models import Review, ReviewReply


def visible_product(product_id):
    return get_object_or_404(visible_products().only('id'), pk=product_id)


def review_feed():
    replies = ReviewReply.objects.order_by('created_at', 'pk')
    return Review.objects.prefetch_related(Prefetch('replies', queryset=replies)).order_by('-created_at', '-pk')


def public_reviews(product_id):
    visible_product(product_id)
    return review_feed().filter(product_id=product_id, is_approved=True)


def owned_reviews(user, *, with_replies=False):
    queryset = review_feed() if with_replies else Review.objects.all()
    return queryset.filter(user=user)


def lock_review(review_id, *, owner=None):
    queryset = Review.objects.all() if owner is None else owned_reviews(owner)
    return get_object_or_404(queryset.select_for_update(), pk=review_id)

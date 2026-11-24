from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException

from core.admin_api import audit
from .models import Review, ReviewReply
from .selectors import lock_review, visible_product


class DuplicateReview(APIException):
    status_code = 409
    default_detail = 'You already reviewed this product.'
    default_code = 'duplicate_review'


@transaction.atomic
def create_review(user, product_id, values):
    product = visible_product(product_id)
    review, created = Review.objects.get_or_create(user=user, product=product, defaults=values)
    if not created:
        raise DuplicateReview()
    return review


@transaction.atomic
def edit_review(user, review_id, values):
    review = lock_review(review_id, owner=user)
    if any(getattr(review, key) != value for key, value in values.items()):
        for key, value in values.items():
            setattr(review, key, value)
        review.is_approved = False
        review.moderated_at = None
        review.save(update_fields=[*values, 'is_approved', 'moderated_at', 'updated_at'])
    return review


@transaction.atomic
def delete_review(user, review_id):
    lock_review(review_id, owner=user).delete()


@transaction.atomic
def moderate_review(actor, review_id, approved):
    review = lock_review(review_id)
    review.is_approved = approved
    review.moderated_at = timezone.now()
    review.save(update_fields=['is_approved', 'moderated_at', 'updated_at'])
    audit(actor, 'approve' if approved else 'reject', review)
    return review


@transaction.atomic
def reply_to_review(actor, review_id, comment):
    review = lock_review(review_id)
    reply = ReviewReply.objects.create(review=review, author=actor, comment=comment)
    audit(actor, 'reply', reply)
    return reply

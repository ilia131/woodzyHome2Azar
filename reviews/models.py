from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Review(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=160)
    comment = models.TextField(max_length=4000)
    is_approved = models.BooleanField(default=False, db_index=True)
    moderated_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', '-created_at', '-id'], condition=models.Q(is_approved=True),
                         name='reviews_public_product_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='one_review_per_product'),
            models.CheckConstraint(condition=models.Q(rating__range=(1, 5)), name='review_valid_rating'),
        ]


class ReviewReply(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='replies')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    comment = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)


    def clean(self):
        if self.parent_id and (self.parent.review_id != self.review_id or self.parent_id == self.pk):
            raise ValidationError({'parent': 'Reply parent must be a different reply to the same review.'})

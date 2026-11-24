from django.conf import settings
from django.db import models


class Favorite(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='favorites')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorites')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'product'], name='one_favorite_per_product')]

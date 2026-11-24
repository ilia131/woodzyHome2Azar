from django.db import models


class ProductView(models.Model):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='views')
    visitor_key = models.CharField(max_length=64)
    authenticated = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'created_at']),
            models.Index(fields=['visitor_key', '-created_at'], condition=models.Q(authenticated=True),
                         name='analytics_account_views_idx'),
        ]

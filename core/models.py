import uuid

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=32)
    model_label = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        permissions = [('view_store_metrics', 'Can view store metrics')]


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f'Contact #{self.pk}'


class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    active = models.BooleanField(default=False)
    revision = models.UUIDField(default=uuid.uuid4, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Subscription #{self.pk}'

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        SUCCEEDED = 'succeeded', 'Succeeded'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
        REFUND_PENDING = 'refund_pending', 'Refund pending'
        REFUNDED = 'refunded', 'Refunded'
        PARTIALLY_REFUNDED = 'partially_refunded', 'Partially refunded'
        REQUIRES_REVIEW = 'requires_review', 'Requires review'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='payments')
    merchant_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider = models.SlugField()
    amount = models.DecimalField(max_digits=32, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=24, choices=Status, default=Status.CREATED)
    idempotency_key = models.UUIDField()
    provider_reference = models.CharField(max_length=128, blank=True)
    payment_url = models.URLField(max_length=500, blank=True)
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True)
    review_reason = models.CharField(max_length=48, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at']), models.Index(fields=['status', 'updated_at'])]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='payment_positive_amount'),
            models.UniqueConstraint(fields=['user', 'idempotency_key'], name='payment_user_idempotency'),
            models.UniqueConstraint(fields=['provider', 'provider_reference'], condition=~Q(provider_reference=''),
                                    name='payment_provider_reference_unique'),
            models.UniqueConstraint(fields=['order'], condition=Q(status__in=['created', 'pending', 'processing']),
                                    name='payment_one_active_per_order'),
            models.UniqueConstraint(fields=['order'], condition=Q(status__in=[
                'succeeded', 'refund_pending', 'refunded', 'partially_refunded',
            ]), name='payment_one_settled_per_order'),
        ]


class PaymentTransaction(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='transactions')
    provider = models.SlugField()
    provider_transaction_id = models.CharField(max_length=128, blank=True)
    transaction_type = models.CharField(max_length=24)
    status = models.CharField(max_length=24)
    amount = models.DecimalField(max_digits=32, decimal_places=2)
    error_code = models.CharField(max_length=48, blank=True)
    sanitized_metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=['provider', 'provider_transaction_id'],
            condition=Q(transaction_type='capture') & ~Q(provider_transaction_id=''),
            name='payment_unique_capture_reference',
        )]


class PaymentWebhookEvent(models.Model):
    provider = models.SlugField()
    event_id = models.UUIDField()
    reference = models.CharField(max_length=128)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT)
    status = models.CharField(max_length=24)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)
    sanitized_metadata = models.JSONField(default=dict)
    error_code = models.CharField(max_length=48, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['provider', 'event_id'], name='payment_webhook_event_once')]


class MockSession(models.Model):
    merchant_id = models.UUIDField(unique=True)
    reference = models.CharField(max_length=128, unique=True)
    amount = models.DecimalField(max_digits=32, decimal_places=2)
    currency = models.CharField(max_length=3)
    state = models.CharField(max_length=24, default='pending')
    scenario = models.CharField(max_length=24, blank=True)
    event_id = models.UUIDField(default=uuid.uuid4)


class Refund(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    idempotency_key = models.UUIDField()
    amount = models.DecimalField(max_digits=32, decimal_places=2)
    status = models.CharField(max_length=24, default='requested')
    provider_reference = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='refund_positive_amount'),
            models.UniqueConstraint(fields=['payment', 'idempotency_key'], name='refund_idempotency'),
        ]

import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Payment
from .providers import provider_for
from .providers.base import ProviderRejected, ProviderUnavailable
from .services import ACTIVE, S, apply_result, finish_initiation, record, transition


logger = logging.getLogger(__name__)


@transaction.atomic
def expire_attempt(pk):
    payment = Payment.objects.select_for_update().get(pk=pk)
    if payment.status in ACTIVE and payment.expires_at <= timezone.now():
        transition(payment, S.EXPIRED, reason='deadline_passed')
        record(payment, 'reconciliation', S.EXPIRED)


@shared_task(acks_late=True)
def reconcile_payments():
    if not settings.PAYMENT_MOCK_ENABLED or settings.PAYMENT_MODE not in {'development', 'test'}:
        return 0
    candidates = Payment.objects.filter(provider='mock').filter(
        Q(status__in=ACTIVE) | Q(status=S.EXPIRED, review_reason='deadline_passed'),
    ).order_by('updated_at', 'pk')[:100]
    count = 0
    for payment in candidates:
        adapter = provider_for(payment.provider)
        try:
            result = adapter.get_payment_status(payment)
            if not payment.provider_reference:
                if result is not None or (payment.status in ACTIVE and payment.expires_at > timezone.now()):
                    payment = finish_initiation(payment.pk, adapter.initiate_payment(payment))
            if result is not None and payment.provider_reference:
                apply_result(payment.pk, result)
            expire_attempt(payment.pk)
            # Fair rotation for attempts that may still get a delayed result.
            Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now())
            count += 1
        except (ProviderUnavailable, ProviderRejected):
            expire_attempt(payment.pk)
            Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now())
            logger.warning('Payment %s remains uncertain', payment.pk)
    return count

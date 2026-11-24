from datetime import timedelta
from decimal import localcontext

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from core.admin_api import audit
from orders.inventory import active_reservations, allocate_verified_order, InventoryConflict
from orders.models import Order
from orders.services import lock_customer
from .models import Payment, PaymentTransaction, PaymentWebhookEvent, Refund
from .providers import provider_for
from .providers.base import ProviderRejected, ProviderUnavailable


S = Payment.Status
ACTIVE = {S.CREATED, S.PENDING, S.PROCESSING}
SETTLED = {S.SUCCEEDED, S.REFUND_PENDING, S.REFUNDED, S.PARTIALLY_REFUNDED}
TRANSITIONS = {
    S.CREATED: {S.PENDING, S.PROCESSING, S.SUCCEEDED, S.FAILED, S.CANCELLED, S.EXPIRED, S.REQUIRES_REVIEW},
    S.PENDING: {S.PROCESSING, S.SUCCEEDED, S.FAILED, S.CANCELLED, S.EXPIRED, S.REQUIRES_REVIEW},
    S.PROCESSING: {S.PENDING, S.SUCCEEDED, S.FAILED, S.CANCELLED, S.EXPIRED, S.REQUIRES_REVIEW},
    S.FAILED: {S.SUCCEEDED, S.REQUIRES_REVIEW},
    S.CANCELLED: {S.SUCCEEDED, S.REQUIRES_REVIEW},
    S.EXPIRED: {S.SUCCEEDED, S.REQUIRES_REVIEW, S.FAILED, S.CANCELLED},
    S.SUCCEEDED: {S.REFUND_PENDING},
    S.PARTIALLY_REFUNDED: {S.REFUND_PENDING},
    S.REFUND_PENDING: {S.REFUNDED, S.PARTIALLY_REFUNDED, S.REQUIRES_REVIEW},
    S.REQUIRES_REVIEW: {S.REFUND_PENDING},
}


class PaymentConflict(APIException):
    status_code = 409


def record(payment, kind, status, *, code='', reference=''):
    return PaymentTransaction.objects.create(
        payment=payment, provider=payment.provider, transaction_type=kind, status=status,
        amount=payment.amount, error_code=code, provider_transaction_id=reference,
        sanitized_metadata={'simulated': payment.provider == 'mock'},
    )


def transition(payment, status, *, reason='', actor=None):
    if status == payment.status:
        return
    if status not in TRANSITIONS.get(payment.status, set()):
        raise PaymentConflict('Invalid payment transition.')
    payment.status = status
    payment.review_reason = reason
    if status == S.SUCCEEDED:
        payment.completed_at = timezone.now()
    payment.save(update_fields=['status', 'review_reason', 'completed_at', 'updated_at'])
    audit(actor, 'payment_transition', payment, metadata={'status': status, 'reason': reason})


@transaction.atomic
def create_attempt(user, order_id, provider, key):
    user = lock_customer(user)
    order = get_object_or_404(Order.objects.select_for_update(), pk=order_id, user=user)
    previous = Payment.objects.filter(user=user, idempotency_key=key).first()
    if previous:
        if previous.order_id != order.pk or previous.provider != provider:
            raise PaymentConflict('Idempotency key is bound to another operation.')
        return previous, False
    if order.status != Order.Status.PENDING_PAYMENT or order.total_amount <= 0 or order.payments.filter(
        Q(status__in=ACTIVE | SETTLED | {S.REQUIRES_REVIEW})
        | Q(status=S.EXPIRED, review_reason='deadline_passed'),
    ).exists():
        raise PaymentConflict('Order is not eligible for a new payment.')
    holds = list(active_reservations(order))
    now = timezone.now()
    if not holds or len(holds) != order.items.count() or any(hold.expires_at <= now for hold in holds):
        raise PaymentConflict('Order has no valid reservation.')
    payment = Payment.objects.create(user=user, order=order, provider=provider, idempotency_key=key,
                                     amount=order.total_amount, currency=order.currency,
                                     expires_at=min(min(h.expires_at for h in holds), now + timedelta(
                                         seconds=settings.PAYMENT_PENDING_EXPIRATION_SECONDS)))
    audit(user, 'payment_created', payment)
    return payment, True


@transaction.atomic
def finish_initiation(payment_id, result=None, *, uncertain=False):
    # This step touches only the attempt and never acquires an order lock afterwards.
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    recovering_expired = payment.status == S.EXPIRED and not payment.provider_reference and result is not None
    if payment.status not in {S.CREATED, S.PROCESSING} and not recovering_expired:
        return payment
    if result is not None:
        payment.provider_reference, payment.payment_url = result.reference, result.url
        payment.save(update_fields=['provider_reference', 'payment_url', 'updated_at'])
        state = S.EXPIRED if recovering_expired else S.PENDING
    else:
        state = S.PROCESSING if uncertain else S.FAILED
    transition(payment, state, reason='initiation_uncertain' if uncertain else '')
    record(payment, 'initiation', state)
    return payment


def initiate(user, order_id, provider, idempotency_key):
    adapter = provider_for(provider)
    payment, created = create_attempt(user, order_id, provider, idempotency_key)
    if not created:
        return payment, False
    try:
        result = adapter.initiate_payment(payment)
    except ProviderUnavailable:
        return finish_initiation(payment.pk, uncertain=True), True
    except ProviderRejected:
        return finish_initiation(payment.pk), True
    return finish_initiation(payment.pk, result), True


def mark_order_review(order):
    if order.status in {Order.Status.PENDING_PAYMENT, Order.Status.EXPIRED}:
        order.status = Order.Status.PAYMENT_REVIEW
        order.save(update_fields=['status', 'updated_at'])
        audit(None, 'order_payment_review', order)


@transaction.atomic
def apply_result(payment_id, result, *, event_id=None, verification_error=''):
    order_id = Payment.objects.values_list('order_id', flat=True).get(pk=payment_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    event = None
    if event_id:
        event, _ = PaymentWebhookEvent.objects.get_or_create(
            provider=payment.provider, event_id=event_id,
            defaults={'payment': payment, 'reference': payment.provider_reference, 'status': 'received'},
        )
        if event.payment_id != payment.pk:
            raise PaymentConflict('Event is bound to another payment.')
        if event.processed_at:
            return payment

    error = verification_error
    if result is not None and (
        result.reference != payment.provider_reference or result.merchant_id != payment.merchant_id
        or result.amount != payment.amount or result.currency != payment.currency
        or (result.status == S.SUCCEEDED and not result.transaction_id)
    ):
        error = 'verification_mismatch'
    if error:
        if payment.status in ACTIVE:
            if error == 'verification_mismatch':
                transition(payment, S.REQUIRES_REVIEW, reason=error)
                if result and result.status == S.SUCCEEDED:
                    mark_order_review(order)
            else:
                transition(payment, S.PROCESSING, reason=error)
        if event or not payment.transactions.filter(transaction_type='verification', error_code=error).exists():
            if not event or event.error_code != error:
                record(payment, 'verification', 'error', code=error)
    elif result is not None and payment.status not in SETTLED | {S.REQUIRES_REVIEW}:
        if result.status == S.SUCCEEDED:
            capture, _ = PaymentTransaction.objects.get_or_create(
                provider=payment.provider, provider_transaction_id=result.transaction_id, transaction_type='capture',
                defaults={'payment': payment, 'amount': payment.amount, 'status': 'verified',
                          'sanitized_metadata': {'simulated': payment.provider == 'mock'}},
            )
            reason = ''
            if capture.payment_id != payment.pk:
                reason = 'duplicate_provider_transaction'
            elif order.payments.exclude(pk=payment.pk).filter(status__in=SETTLED).exists():
                reason = 'order_already_settled'
            else:
                try:
                    allocate_verified_order(order.pk)
                except InventoryConflict:
                    reason = 'inventory_unavailable'
            if reason:
                transition(payment, S.REQUIRES_REVIEW, reason=reason)
                mark_order_review(order)
            else:
                order.status = Order.Status.PAID
                order.save(update_fields=['status', 'updated_at'])
                audit(None, 'order_paid', order, metadata={'payment_id': payment.pk})
                transition(payment, S.SUCCEEDED)
        elif result.status in {S.FAILED, S.CANCELLED, S.EXPIRED} and (
            payment.status in ACTIVE or (payment.status == S.EXPIRED and payment.review_reason == 'deadline_passed')
        ):
            if payment.status == result.status:
                payment.review_reason = ''
                payment.save(update_fields=['review_reason', 'updated_at'])
            else:
                transition(payment, result.status)
            record(payment, 'verification', result.status)

    if event:
        event.status = 'retry' if error == 'verification_unavailable' else ('rejected' if error else 'processed')
        event.processed_at = None if event.status == 'retry' else timezone.now()
        event.error_code = error
        event.save(update_fields=['status', 'processed_at', 'error_code'])
    return payment


def callback(provider, payload, signature):
    adapter = provider_for(provider)
    try:
        event, reference = adapter.process_callback(payload, signature)
    except ProviderRejected as exc:
        raise PermissionDenied('Invalid callback.') from exc
    payment = Payment.objects.filter(provider=provider, provider_reference=reference).first()
    if not payment:
        raise NotFound('Unknown payment reference.')
    try:
        result = adapter.verify_payment(reference)
    except (ProviderUnavailable, ProviderRejected):
        return apply_result(payment.pk, None, event_id=event, verification_error='verification_unavailable')
    return apply_result(payment.pk, result, event_id=event)


@transaction.atomic
def request_refund(payment_id, actor, amount, key):
    order_id = Payment.objects.values_list('order_id', flat=True).filter(pk=payment_id).first()
    order = get_object_or_404(Order.objects.select_for_update(), pk=order_id)
    payment = Payment.objects.select_for_update().get(pk=payment_id, order=order)
    previous = payment.refunds.filter(idempotency_key=key).first()
    if previous:
        if previous.amount != amount or previous.requested_by_id != actor.pk:
            raise PaymentConflict('Refund key is bound to another request.')
        return previous
    captures = payment.transactions.filter(transaction_type='capture', status='verified').exists()
    if not captures or payment.status not in SETTLED | {S.REQUIRES_REVIEW}:
        raise PaymentConflict('No verified capture is available to refund.')
    with localcontext() as money:
        money.prec = 36
        allocated = sum(payment.refunds.exclude(status='rejected').values_list('amount', flat=True))
        if amount <= 0 or allocated + amount > payment.amount:
            raise PaymentConflict('Refund amount exceeds the remaining captured balance.')
    refund = Refund.objects.create(payment=payment, requested_by=actor, amount=amount, idempotency_key=key)
    if payment.status != S.REQUIRES_REVIEW:
        transition(payment, S.REFUND_PENDING, actor=actor)
    audit(actor, 'refund_requested', refund)
    PaymentTransaction.objects.create(payment=payment, provider=payment.provider, transaction_type='refund_request',
                                      status='requested', amount=amount,
                                      sanitized_metadata={'simulated': payment.provider == 'mock'})
    return refund


def simulate_refund(payment_id, refund_id, actor):
    adapter = provider_for('mock')
    refund = get_object_or_404(Refund.objects.select_related('payment'), pk=refund_id,
                               payment_id=payment_id, payment__provider='mock')
    reference = adapter.refund_payment(refund)
    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund.pk)
        if refund.status == 'simulated':
            return refund
        if refund.status != 'requested':
            raise PaymentConflict('Refund is not eligible for simulation.')
        refund.provider_reference = reference
        refund.status = 'simulated'
        refund.save(update_fields=['provider_reference', 'status'])
        PaymentTransaction.objects.create(payment=refund.payment, provider='mock', provider_transaction_id=reference,
                                          transaction_type='refund_simulation', status='simulated',
                                          amount=refund.amount, sanitized_metadata={'simulated': True})
        audit(actor, 'refund_simulated', refund)
        return refund

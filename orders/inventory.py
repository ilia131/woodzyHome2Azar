import logging
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import APIException

from core.admin_api import audit
from products.models import Product, ProductChange
from .models import InventoryMovement, Order, Reservation


logger = logging.getLogger(__name__)

MAX_STOCK = 2147483647


class InventoryConflict(APIException):
    status_code = 409


def lock_products(ids):
    return {product.pk: product for product in Product.objects.filter(pk__in=ids).order_by('pk').select_for_update()}


def write_stock(product, value):
    product.stock = value
    product.save(update_fields=['stock', 'updated_at'])


def movement(product, kind, delta, key, *, actor=None, reservation=None):
    return InventoryMovement.objects.create(
        product=product, product_id_snapshot=product.pk, kind=kind, quantity=abs(delta),
        available_delta=delta, available_after=product.stock, operation_key=key, actor=actor,
        reservation=reservation, order_id=reservation.order_id if reservation else None,
        item_id=reservation.item_id if reservation else None,
    )


def record_initial_stock(product, actor):
    if product.stock:
        movement(product, InventoryMovement.Kind.INITIAL, product.stock, f'initial:{product.pk}', actor=actor)


@transaction.atomic
def create_catalog_product(values, actor):
    product = Product.objects.create(**values)
    record_initial_stock(product, actor)
    return product


def stock_revision(product_id):
    return ProductChange.objects.filter(product_id=product_id).order_by('-pk').values_list('pk', flat=True).first()


@transaction.atomic
def adjust_available(product_id, actor, *, target=None, delta=None, expected_revision=None,
                     operation_id=None, catalog_fields=None):
    product = get_object_or_404(Product.objects.select_for_update(), pk=product_id)
    key = f'adjust:{product_id}:{operation_id or uuid4().hex}'
    if operation_id:
        previous = InventoryMovement.objects.filter(operation_key=key).first()
        if previous:
            matches = (previous.metadata.get('target') == target
                       and previous.metadata.get('expected_revision') == expected_revision) if target is not None else (
                           'target' not in previous.metadata and previous.available_delta == delta)
            if not matches or previous.actor_id != actor.pk:
                raise InventoryConflict('This operation ID is already in use.')
            return previous
    if target is not None and (expected_revision is None or expected_revision != stock_revision(product.pk)):
        raise InventoryConflict('Stock changed. Refresh the product and confirm the adjustment again.')
    change = target - product.stock if target is not None else delta
    if catalog_fields:
        for field, value in catalog_fields.items():
            setattr(product, field, value)
    if not change:
        if operation_id:
            raise InventoryConflict('The requested stock is already available.')
        if catalog_fields:
            product.save()
        return None
    updated = product.stock + change
    reserved = Reservation.objects.filter(product=product, status=Reservation.Status.ACTIVE).aggregate(
        total=Sum('quantity', default=0),
    )['total']
    if not 0 <= updated <= MAX_STOCK - reserved:
        raise InventoryConflict('The adjustment would put inventory outside its allowed range.')
    if catalog_fields:
        product.stock = updated
        product.save()
    else:
        write_stock(product, updated)
    event = movement(product, InventoryMovement.Kind.ADJUST, change, key, actor=actor)
    if target is not None:
        event.metadata = {'target': target, 'expected_revision': expected_revision}
        event.save(update_fields=['metadata'])
    audit(actor, 'inventory_adjust', product, metadata={'movement_id': event.pk, 'delta': change})
    return event


def reserve_items(order, items, products, actor):
    now = timezone.now()
    expires = now + timedelta(seconds=settings.INVENTORY_RESERVATION_SECONDS)
    for item in sorted(items, key=lambda item: item.product_id):
        product = products[item.product_id]
        if item.quantity > product.stock:
            raise InventoryConflict('A cart quantity exceeds available stock.')
        write_stock(product, product.stock - item.quantity)
        reservation = Reservation.objects.create(order=order, item=item, product=product, quantity=item.quantity,
                                                 reserved_at=now, expires_at=expires)
        movement(product, InventoryMovement.Kind.RESERVE, -item.quantity, f'reserve:{reservation.pk}',
                 actor=actor, reservation=reservation)
    audit(actor, 'inventory_reserve', order, metadata={'item_count': len(items)})


def release_reservations(order, reservations, now, *, expired, actor=None):
    products = lock_products(row.product_id for row in reservations)
    kind = InventoryMovement.Kind.EXPIRE if expired else InventoryMovement.Kind.RELEASE
    status = Reservation.Status.EXPIRED if expired else Reservation.Status.RELEASED
    for row in reservations:
        product = products[row.product_id]
        write_stock(product, product.stock + row.quantity)
        row.status = status
        row.released_at = now
        row.save(update_fields=['status', 'released_at', 'updated_at'])
        movement(product, kind, row.quantity, f'finish:{row.pk}', actor=actor, reservation=row)
    if expired and order.status == Order.Status.PENDING_PAYMENT and not order.reservations.filter(
        status=Reservation.Status.ACTIVE,
    ).exists():
        order.status = Order.Status.EXPIRED
        order.save(update_fields=['status', 'updated_at'])
    audit(actor, 'inventory_expire' if expired else 'inventory_release', order,
          metadata={'item_count': len(reservations)})


def active_reservations(order):
    return order.reservations.select_for_update().filter(status=Reservation.Status.ACTIVE).order_by('product_id', 'pk')


@transaction.atomic
def expire_order(order_id):
    order = Order.objects.select_for_update().get(pk=order_id)
    now = timezone.now()
    rows = list(active_reservations(order).filter(expires_at__lte=now))
    if rows:
        release_reservations(order, rows, now, expired=True)
    return len(rows)


@transaction.atomic
def cancel_order(user, order_id):
    order = get_object_or_404(Order.objects.select_for_update(), pk=order_id, user=user)
    return cancel_locked_order(order, user)


def cancel_locked_order(order, actor):
    if order.status != Order.Status.PENDING_PAYMENT:
        raise InventoryConflict('This order cannot be cancelled.')
    now = timezone.now()
    rows = list(active_reservations(order))
    if not rows:
        raise InventoryConflict('This order has no active reservation.')
    due = [row for row in rows if row.expires_at <= now]
    if due:
        release_reservations(order, due, now, expired=True)
        # The caller returns 409 after the expiration transaction commits.
        return None
    release_reservations(order, rows, now, expired=False, actor=actor)
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    audit(actor, 'order_cancel', order)
    return order


@transaction.atomic
def consume_order_reservations(order_id, actor=None):
    """Internal integration point for a future verified payment workflow."""
    order = Order.objects.select_for_update().get(pk=order_id)
    rows = list(active_reservations(order))
    now = timezone.now()
    if (order.status != Order.Status.PENDING_PAYMENT or not rows or len(rows) != order.items.count()
            or any(row.expires_at <= now for row in rows)):
        raise InventoryConflict('No valid reservations are available to consume.')
    products = lock_products(row.product_id for row in rows)
    for row in rows:
        row.status = Reservation.Status.CONSUMED
        row.consumed_at = now
        row.save(update_fields=['status', 'consumed_at', 'updated_at'])
        product = products[row.product_id]
        InventoryMovement.objects.create(
            product=product, product_id_snapshot=product.pk, order=order, item_id=row.item_id, reservation=row,
            kind=InventoryMovement.Kind.CONSUME, quantity=row.quantity, available_delta=0,
            available_after=product.stock, actor=actor, operation_key=f'finish:{row.pk}',
        )
    audit(actor, 'inventory_consume', order, metadata={'item_count': len(rows)})


def expire_due(*, product_ids=None):
    due = Reservation.objects.filter(status=Reservation.Status.ACTIVE, expires_at__lte=timezone.now())
    if product_ids is not None:
        due = due.filter(product_id__in=product_ids)
    count = 0
    order_ids = due.order_by('order_id').values_list('order_id', flat=True).distinct()
    # Keyset batches avoid keeping a cursor open across per-order transactions.
    last_id = 0
    while batch := list(order_ids.filter(order_id__gt=last_id)[:200]):
        for order_id in batch:
            try:
                count += expire_order(order_id)
            except DatabaseError:
                logger.exception('Failed to expire order %s; retry on the next run', order_id)
        last_id = batch[-1]
    return count


@transaction.atomic
def allocate_verified_order(order_id):
    """Consume live holds or re-reserve the entire expired order before consumption."""
    order = Order.objects.select_for_update().get(pk=order_id)
    now = timezone.now()
    if order.status not in {Order.Status.PENDING_PAYMENT, Order.Status.EXPIRED}:
        raise InventoryConflict('Order is no longer eligible for allocation.')
    rows = list(active_reservations(order))
    if rows and all(row.expires_at > now for row in rows):
        consume_order_reservations(order.pk)
        return
    items = list(order.items.order_by('product_id'))
    if not items or any(item.product_id is None for item in items):
        raise InventoryConflict('Order inventory is unavailable.')
    from products.selectors import visible_products

    products = lock_products(item.product_id for item in items)
    if rows:
        if any(row.expires_at > now for row in rows):
            raise InventoryConflict('Order has mixed reservation deadlines.')
        release_reservations(order, rows, now, expired=True)
        products = lock_products(products)
    if not order.reservations.filter(status=Reservation.Status.EXPIRED).exists():
        raise InventoryConflict('Order has no expired holds to replace.')
    visible = set(visible_products().filter(pk__in=products).values_list('pk', flat=True))
    if any(item.product_id not in visible or products[item.product_id].stock < item.quantity for item in items):
        raise InventoryConflict('Order inventory is unavailable.')
    order.status = Order.Status.PENDING_PAYMENT
    order.save(update_fields=['status', 'updated_at'])
    reserve_items(order, items, products, None)
    consume_order_reservations(order.pk)

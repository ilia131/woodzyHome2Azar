from django.db import transaction
from django.shortcuts import get_object_or_404

from core.admin_api import audit
from .inventory import InventoryConflict, cancel_locked_order
from .models import Order

FULFILLMENT = {
    Order.Status.PAID: Order.Status.PROCESSING,
    Order.Status.PROCESSING: Order.Status.COMPLETED,
}


@transaction.atomic
def staff_transition(actor, order_id, expected_status, status):
    order = get_object_or_404(Order.objects.select_for_update(), pk=order_id)
    if order.status != expected_status:
        raise InventoryConflict('Order status changed. Reload it before retrying.')
    if status == Order.Status.CANCELLED and order.status == Order.Status.PENDING_PAYMENT:
        return cancel_locked_order(order, actor)
    if FULFILLMENT.get(order.status) != status:
        raise InventoryConflict('This transition is not allowed.')
    order.status = status
    order.save(update_fields=['status', 'updated_at'])
    audit(actor, 'order_status_change', order, metadata={'from': expected_status, 'to': status})
    return order

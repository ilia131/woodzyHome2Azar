from decimal import Decimal, localcontext
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException

from core.admin_api import audit
from products.selectors import visible_products
from .inventory import expire_due, lock_products, reserve_items
from .models import Order, OrderItem
from .selectors import owned_addresses, owned_cart_items
from .services import lock_customer


class CheckoutConflict(APIException):
    status_code = 409


SHIPPING_FIELDS = ('recipient_name', 'recipient_phone', 'province', 'city', 'address_line', 'postal_code')


def snapshot_item(cart_item):
    product = cart_item.product
    if not cart_item.product_visible:
        raise CheckoutConflict('A cart product is no longer available.')
    if cart_item.quantity < 1 or cart_item.quantity > product.stock:
        raise CheckoutConflict('A cart quantity is no longer valid for current stock.')
    return OrderItem(
        product=product,
        product_title=product.title,
        product_slug=product.slug,
        product_sku=product.sku,
        product_main_image=product.main_image.name or '',
        unit_price=product.effective_price,
        quantity=cart_item.quantity,
        line_total=product.effective_price * cart_item.quantity,
    )


def place_order(user, address_id):
    # Reclaim expired holds before acquiring checkout locks.
    expire_due(product_ids=owned_cart_items(user).values('product_id'))
    return place_order_locked(user, address_id)


@transaction.atomic
def place_order_locked(user, address_id):
    account = lock_customer(user)
    address = get_object_or_404(owned_addresses(account), pk=address_id)
    rows = list(owned_cart_items(account).order_by('pk'))
    if not rows:
        raise CheckoutConflict('The cart is empty.')

    product_ids = [row.product_id for row in rows]
    products = lock_products(product_ids)
    visible = set(visible_products().filter(pk__in=product_ids).values_list('pk', flat=True))
    for row in rows:
        if row.product_id not in visible:
            raise CheckoutConflict('A cart product is no longer available.')
        row.product = products[row.product_id]
        row.product_visible = True

    with localcontext() as money:
        money.prec = 32
        items = [snapshot_item(row) for row in rows]
        subtotal = sum((item.line_total for item in items), Decimal('0.00'))
    order = Order.objects.create(
        user=account,
        order_number=uuid4().hex,
        shipping_address=address,
        shipping_address_snapshot={field: getattr(address, field) for field in SHIPPING_FIELDS},
        currency=settings.CURRENCY,
        subtotal=subtotal,
        total_amount=subtotal,
    )
    for item in items:
        item.order = order
    OrderItem.objects.bulk_create(items)
    reserve_items(order, items, products, account)
    audit(account, 'order_create', order, metadata={'order_number': order.order_number, 'item_count': len(items)})
    owned_cart_items(account).filter(pk__in=[row.pk for row in rows]).delete()
    return order

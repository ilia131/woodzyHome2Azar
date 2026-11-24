from django.db.models import Exists, OuterRef

from products.selectors import visible_products
from .models import Address, CartItem, Order


def owned_addresses(user):
    return Address.objects.filter(user=user).order_by('-is_default', '-created_at', '-pk')


def owned_cart_items(user):
    return CartItem.objects.filter(user=user)


def cart_items(user):
    visible = visible_products().filter(pk=OuterRef('product_id'))
    return owned_cart_items(user).select_related('product').annotate(
        product_visible=Exists(visible),
    ).order_by('-created_at', '-pk')


def owned_orders(user):
    return Order.objects.filter(user=user).prefetch_related('items').order_by('-created_at', '-pk')

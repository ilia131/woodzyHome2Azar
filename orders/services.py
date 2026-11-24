from django.conf import settings
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import APIException, AuthenticationFailed, ValidationError

from accounts.models import User
from core.admin_api import audit
from products.selectors import visible_products
from .models import Address, CartItem
from .selectors import owned_addresses, owned_cart_items


class CartStockConflict(APIException):
    status_code = 409
    default_detail = 'The requested quantity exceeds current stock.'
    default_code = 'insufficient_stock'


def lock_customer(user):
    # Account before any product lock. Future checkout should use the same order.
    account = get_object_or_404(User.objects.select_for_update(), pk=user.pk)
    if not account.is_active or account.session_version != user.session_version:
        raise AuthenticationFailed('The account session has been revoked.')
    return account


def clear_default(user):
    previous = owned_addresses(user).filter(is_default=True).first()
    if previous is not None:
        previous.is_default = False
        previous.save(update_fields=['is_default', 'updated_at'])
        audit(user, 'address_unset_default', previous)


@transaction.atomic
def create_address(user, values):
    account = lock_customer(user)
    values = dict(values)
    default = values.pop('is_default', False) or not owned_addresses(account).filter(is_default=True).exists()
    if default:
        clear_default(account)
    address = Address.objects.create(user=account, is_default=default, **values)
    audit(account, 'address_create', address)
    return address


@transaction.atomic
def edit_address(user, address_id, values):
    account = lock_customer(user)
    address = get_object_or_404(owned_addresses(account), pk=address_id)
    if values.get('is_default') is False and address.is_default:
        raise ValidationError({'is_default': 'Select another default address first.'})
    changes = {name: value for name, value in values.items() if getattr(address, name) != value}
    if changes.get('is_default'):
        clear_default(account)
    if changes:
        for name, value in changes.items():
            setattr(address, name, value)
        address.save(update_fields=[*changes, 'updated_at'])
        audit(account, 'address_update', address)
    return address


@transaction.atomic
def delete_address(user, address_id):
    account = lock_customer(user)
    address = get_object_or_404(owned_addresses(account), pk=address_id)
    was_default = address.is_default
    audit(account, 'address_delete', address)
    address.delete()
    if was_default:
        replacement = owned_addresses(account).order_by('created_at', 'pk').first()
        if replacement is not None:
            replacement.is_default = True
            replacement.save(update_fields=['is_default', 'updated_at'])
            audit(account, 'address_set_default', replacement)


def available_product(product_id, quantity):
    product = get_object_or_404(visible_products().select_for_update(), pk=product_id)
    if quantity > product.stock:
        raise CartStockConflict()
    return product


def save_quantity(item, product, quantity):
    if item.quantity != quantity:
        item.quantity = quantity
        item.save(update_fields=['quantity', 'updated_at'])
        audit(item.user, 'cart_update', item)
    item.product = product
    item.product_visible = True
    return item


@transaction.atomic
def upsert_cart_item(user, product_id, quantity):
    account = lock_customer(user)
    product = available_product(product_id, quantity)
    item, created = CartItem.objects.get_or_create(user=account, product=product, defaults={'quantity': quantity})
    if created:
        audit(account, 'cart_add', item)
    return save_quantity(item, product, quantity), created


@transaction.atomic
def update_cart_quantity(user, item_id, quantity):
    account = lock_customer(user)
    item = get_object_or_404(owned_cart_items(account), pk=item_id)
    product = available_product(item.product_id, quantity)
    return save_quantity(item, product, quantity)


@transaction.atomic
def remove_cart_item(user, item_id):
    account = lock_customer(user)
    item = get_object_or_404(owned_cart_items(account), pk=item_id)
    audit(account, 'cart_remove', item)
    item.delete()

def cart_summary(queryset):
    eligible = queryset.filter(product_visible=True, quantity__lte=F('product__stock'))
    line_total = ExpressionWrapper(
        Coalesce('product__discount_price', 'product__price') * F('quantity'),
        output_field=DecimalField(max_digits=26, decimal_places=2),
    )
    counts = eligible.aggregate(available_item_count=Count('pk'), subtotal=Sum(line_total, default=0))
    return {**counts, 'currency': settings.CURRENCY}

from collections.abc import Mapping

import re
import unicodedata

from django.conf import settings
from rest_framework import serializers

from accounts.models import normalize_phone
from .models import Address, CartItem, Order, OrderItem


class AddressSerializer(serializers.ModelSerializer):
    recipient_phone = serializers.CharField(max_length=32)
    postal_code = serializers.CharField(max_length=24)

    class Meta:
        model = Address
        fields = ('id', 'label', 'recipient_name', 'recipient_phone', 'province', 'city', 'address_line',
                  'postal_code', 'is_default', 'created_at', 'updated_at')
        read_only_fields = ('created_at', 'updated_at')

    def validate_recipient_phone(self, value):
        return normalize_phone(value)

    def validate_postal_code(self, value):
        digits = ''.join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in value)
        digits = re.sub(r'[\s-]', '', digits)
        if not re.fullmatch(r'[0-9]{10}', digits):
            raise serializers.ValidationError('Enter a 10-digit Iranian postal code.')
        return digits


class CartQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=2147483647)


class CartItemWriteSerializer(CartQuantitySerializer):
    product_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField()
    product_title = serializers.CharField(allow_null=True, read_only=True)
    unit_price = serializers.DecimalField(max_digits=16, decimal_places=2, allow_null=True, read_only=True)
    line_total = serializers.DecimalField(max_digits=26, decimal_places=2, allow_null=True, read_only=True)
    currency = serializers.SerializerMethodField()
    availability = serializers.ChoiceField(choices=('available', 'insufficient_stock', 'out_of_stock', 'not_visible'),
                                          read_only=True)

    class Meta:
        model = CartItem
        fields = ('id', 'product_id', 'product_title', 'quantity', 'unit_price', 'line_total', 'currency',
                  'availability', 'created_at', 'updated_at')

    def get_currency(self, item) -> str:
        return settings.CURRENCY


class CartSummarySerializer(serializers.Serializer):
    available_item_count = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=32, decimal_places=2)
    currency = serializers.CharField()


class CommerceErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class CheckoutSerializer(serializers.Serializer):
    address_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)

    def to_internal_value(self, data):

        if isinstance(data, Mapping) and set(data) - {'address_id'}:
            raise serializers.ValidationError({'non_field_errors': ['Only address_id may be supplied.']})
        return super().to_internal_value(data)


class ShippingSnapshotSerializer(serializers.Serializer):
    recipient_name = serializers.CharField()
    recipient_phone = serializers.CharField()
    province = serializers.CharField()
    city = serializers.CharField()
    address_line = serializers.CharField()
    postal_code = serializers.CharField()


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = OrderItem
        fields = ('id', 'product_id', 'product_title', 'product_slug', 'product_sku', 'product_main_image',
                  'unit_price', 'quantity', 'line_total', 'created_at')
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    shipping_address_snapshot = ShippingSnapshotSerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ('id', 'order_number', 'shipping_address', 'shipping_address_snapshot', 'status', 'currency',
                  'subtotal', 'discount_amount', 'shipping_amount', 'total_amount', 'items', 'created_at', 'updated_at')
        read_only_fields = fields

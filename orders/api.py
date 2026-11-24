from django.utils.cache import add_never_cache_headers
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.api import Pagination
from .checkout import place_order
from .inventory import InventoryConflict, cancel_order
from .models import Address, CartItem, Order
from .selectors import cart_items, owned_addresses, owned_orders
from .serializers import (
    AddressSerializer, CartItemSerializer, CartItemWriteSerializer, CartQuantitySerializer, CartSummarySerializer,
    CheckoutSerializer, CommerceErrorSerializer, OrderSerializer,
)
from .services import (
    cart_summary, create_address, delete_address, edit_address, remove_cart_item, update_cart_quantity,
    upsert_cart_item,
)


class PrivateCommerceAPI:
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        add_never_cache_headers(response)
        return response


@extend_schema_view(get=extend_schema(description='List the authenticated account’s delivery addresses.'))
class AddressList(PrivateCommerceAPI, generics.ListCreateAPIView):
    queryset = Address.objects.none()
    serializer_class = AddressSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_addresses(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = create_address(self.request.user, serializer.validated_data)


class AddressDetail(PrivateCommerceAPI, generics.RetrieveUpdateDestroyAPIView):
    queryset = Address.objects.none()
    serializer_class = AddressSerializer
    http_method_names = ['get', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_addresses(self.request.user)

    def perform_update(self, serializer):
        serializer.instance = edit_address(self.request.user, self.kwargs['pk'], serializer.validated_data)

    def perform_destroy(self, instance):
        delete_address(self.request.user, instance.pk)


class CartPagination(Pagination):
    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data['summary'] = CartSummarySerializer(cart_summary(self.page.paginator.object_list)).data
        return response

    def get_paginated_response_schema(self, schema):
        result = super().get_paginated_response_schema(schema)
        result['properties']['summary'] = {
            'type': 'object',
            'required': ['available_item_count', 'subtotal', 'currency'],
            'properties': {
                'available_item_count': {'type': 'integer'},
                'subtotal': {'type': 'string', 'format': 'decimal'},
                'currency': {'type': 'string'},
            },
        }
        result['required'].append('summary')
        return result


@extend_schema_view(get=extend_schema(description=(
    'List the caller’s cart with current prices, availability and an estimate across all available lines. '
    'Products are not reserved.')))
class Cart(PrivateCommerceAPI, generics.ListAPIView):
    pagination_class = CartPagination
    queryset = CartItem.objects.none()
    serializer_class = CartItemSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return cart_items(self.request.user)


class CartItems(PrivateCommerceAPI, generics.GenericAPIView):
    serializer_class = CartItemSerializer

    @extend_schema(
        request=CartItemWriteSerializer,
        responses={200: CartItemSerializer, 201: CartItemSerializer, 404: CommerceErrorSerializer, 409: CommerceErrorSerializer},
        description='Add a product or set the absolute quantity of its existing cart line.',
    )
    def post(self, request):
        data = CartItemWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item, created = upsert_cart_item(request.user, **data.validated_data)
        return Response(self.get_serializer(item).data, status=201 if created else 200)


class CartItemDetail(PrivateCommerceAPI, generics.GenericAPIView):
    queryset = CartItem.objects.none()
    serializer_class = CartItemSerializer

    @extend_schema(request=CartQuantitySerializer,
                   responses={200: CartItemSerializer, 404: CommerceErrorSerializer, 409: CommerceErrorSerializer})
    def patch(self, request, pk):
        data = CartQuantitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        item = update_cart_quantity(request.user, pk, data.validated_data['quantity'])
        return Response(self.get_serializer(item).data)

    @extend_schema(responses={204: None, 404: CommerceErrorSerializer})
    def delete(self, request, pk):
        remove_cart_item(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderList(PrivateCommerceAPI, generics.ListAPIView):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_orders(self.request.user)

    @extend_schema(
        request=CheckoutSerializer,
        responses={201: OrderSerializer, 404: CommerceErrorSerializer, 409: CommerceErrorSerializer},
        description='Create an unpaid order from the entire cart and an owned address. '
                    'Uses current catalog prices and clears the cart only on success. Stock is reserved until the stored deadline.',
    )
    def post(self, request):
        data = CheckoutSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = place_order(request.user, **data.validated_data)
        order = self.get_queryset().get(pk=order.pk)
        return Response(self.get_serializer(order).data, status=201)


class OrderDetail(PrivateCommerceAPI, generics.RetrieveAPIView):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_orders(self.request.user)


class OrderCancel(PrivateCommerceAPI, generics.GenericAPIView):
    queryset = Order.objects.none()
    serializer_class = OrderSerializer

    @extend_schema(request=None, responses={200: OrderSerializer, 404: CommerceErrorSerializer,
                                           409: CommerceErrorSerializer},
                   description='Cancel an owned pending order with a live reservation and release its stock.')
    def post(self, request, pk):
        order = cancel_order(request.user, pk)
        if order is None:
            raise InventoryConflict('This reservation has expired.')
        return Response(self.get_serializer(owned_orders(request.user).get(pk=pk)).data)

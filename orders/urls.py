from django.urls import path

from .api import AddressDetail, AddressList, Cart, CartItemDetail, CartItems, OrderCancel, OrderDetail, OrderList

urlpatterns = [
    path("orders/", OrderList.as_view(), name="orders"),
    path("orders/<int:pk>/", OrderDetail.as_view(), name="order-detail"),
    path("orders/<int:pk>/cancel/", OrderCancel.as_view(), name="order-cancel"),
    path('addresses/', AddressList.as_view(), name='addresses'),
    path('addresses/<int:pk>/', AddressDetail.as_view(), name='address-detail'),
    path('cart/', Cart.as_view(), name='cart'),
    path('cart/items/', CartItems.as_view(), name='cart-items'),
    path('cart/items/<int:pk>/', CartItemDetail.as_view(), name='cart-item-detail'),
]

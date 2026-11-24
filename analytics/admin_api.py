from django.contrib.auth.models import AnonymousUser
from categories.api import CategorySerializer
from categories.models import Category
from products.selectors import public_products
from products.serializers import ProductSerializer
from recommendations.services import popular_products, recommended_categories
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from products.models import Product
from .services import view_metrics


class MetricsPermission(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_staff and request.user.has_perm('core.view_store_metrics')


class MetricsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    authenticated = serializers.IntegerField()
    guest = serializers.IntegerField()
    unique = serializers.IntegerField()
    daily = serializers.IntegerField()
    weekly = serializers.IntegerField()
    monthly = serializers.IntegerField()
    last_view_at = serializers.DateTimeField(allow_null=True)


class AdminProductMetrics(generics.GenericAPIView):
    permission_classes = [MetricsPermission]
    serializer_class = MetricsSerializer
    queryset = Product.objects.all()

    def get(self, request, pk):
        product = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(self.get_serializer(view_metrics(product)).data)


class AdminPopularProducts(generics.ListAPIView):
    permission_classes = [MetricsPermission]
    serializer_class = ProductSerializer
    queryset = Product.objects.none()

    def get_queryset(self):
        return popular_products()


class AdminMostViewedProducts(AdminPopularProducts):
    def get_queryset(self):
        return public_products().order_by('-view_count', '-pk')


class AdminPopularCategories(generics.ListAPIView):
    permission_classes = [MetricsPermission]
    serializer_class = CategorySerializer
    queryset = Category.objects.none()

    def get_queryset(self):
        return recommended_categories(AnonymousUser())

from django.db.models import OuterRef, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError

from rest_framework.exceptions import PermissionDenied
from orders.inventory import adjust_available, create_catalog_product
from core.admin_api import CatalogAdminViewSet, StaffModelPermissions
from .models import Product, ProductChange, ProductImage


RESERVED_SLUGS = {'popular', 'most-viewed', 'most-favorited', 'best-discounts', 'recommended', 'best-selling'}


class ProductWriteSerializer(serializers.ModelSerializer):
    stock_revision = serializers.IntegerField(required=False, min_value=1, allow_null=True)

    class Meta:
        model = Product
        fields = ('id', 'title', 'slug', 'short_description', 'description', 'main_image', 'price',
                  'discount_price', 'stock', 'stock_revision', 'sku', 'category', 'is_active', 'is_featured', 'created_at', 'updated_at')

    def create(self, validated_data):
        validated_data.pop('stock_revision', None)
        result = create_catalog_product(validated_data, self.context['request'].user)
        return AdminProducts.queryset.get(pk=result.pk)

    def update(self, instance, validated_data):
        stock = validated_data.pop('stock', None)
        revision = validated_data.pop('stock_revision', None)
        actor = self.context['request'].user
        if stock is not None:
            if not actor.has_perm('orders.add_inventorymovement'):
                raise PermissionDenied('Inventory adjustment permission is required.')
            adjust_available(instance.pk, actor, target=stock, expected_revision=revision, catalog_fields=validated_data)
        else:
            super().update(instance, validated_data)
        return AdminProducts.queryset.get(pk=instance.pk)

    def validate_slug(self, value):
        if value in RESERVED_SLUGS:
            raise serializers.ValidationError('This slug is reserved.')
        if self.instance and value != self.instance.slug:
            raise serializers.ValidationError('A published product URL cannot be changed.')
        return value

    def validate(self, attrs):
        price = attrs.get('price', getattr(self.instance, 'price', None))
        discount = attrs.get('discount_price', getattr(self.instance, 'discount_price', None))
        if discount is not None and price is not None and discount >= price:
            raise serializers.ValidationError({'discount_price': 'Discount price must be below list price.'})
        return attrs


class ImageWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ('id', 'product', 'image', 'alt_text', 'position')


class ProductHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductChange
        fields = ('id', 'product', 'price', 'discount_price', 'stock', 'created_at')


class AdminProducts(CatalogAdminViewSet):
    queryset = Product.objects.select_related('category').annotate(stock_revision=Subquery(
        ProductChange.objects.filter(product_id=OuterRef('pk')).order_by('-pk').values('pk')[:1],
    ))
    serializer_class = ProductWriteSerializer
    search_fields = ('title', 'sku', 'slug')
    ordering_fields = ('id', 'price', 'stock', 'created_at')

    def perform_destroy(self, instance):
        raise ValidationError('Deactivate products to retain their URL and history.')


class AdminImages(CatalogAdminViewSet):
    queryset = ProductImage.objects.select_related('product')
    serializer_class = ImageWriteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ('product',)
    search_fields = ('product__sku', 'alt_text')


class AdminProductHistory(viewsets.ReadOnlyModelViewSet):
    queryset = ProductChange.objects.order_by('-created_at', '-pk')
    serializer_class = ProductHistorySerializer
    permission_classes = [StaffModelPermissions]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ('product',)

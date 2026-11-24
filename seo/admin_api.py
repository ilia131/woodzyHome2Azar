from rest_framework import serializers
from core.admin_api import CatalogAdminViewSet
from .models import ProductSEO


class SEOWriteSerializer(serializers.ModelSerializer):
    structured_data = serializers.DictField(required=False)

    class Meta:
        model = ProductSEO
        fields = ('id', 'product', 'meta_title', 'meta_description', 'meta_keywords', 'canonical_url',
                  'og_title', 'og_description', 'og_image', 'structured_data', 'robots_index', 'robots_follow')


class AdminSEO(CatalogAdminViewSet):
    queryset = ProductSEO.objects.select_related('product')
    serializer_class = SEOWriteSerializer
    search_fields = ('product__sku', 'product__title', 'meta_title')

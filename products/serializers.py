from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from seo.services import metadata
from .models import Product, ProductImage


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ('id', 'image', 'alt_text', 'position')


class ProductSerializer(serializers.ModelSerializer):
    gallery = ImageSerializer(many=True, read_only=True)
    category = serializers.SlugRelatedField(slug_field='slug', read_only=True)
    discount_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    effective_price = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    in_stock = serializers.BooleanField(read_only=True)
    favorite_count = serializers.IntegerField(read_only=True)
    view_count = serializers.IntegerField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    average_rating = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = ('id', 'title', 'slug', 'short_description', 'main_image', 'gallery', 'price',
                  'discount_price', 'discount_percentage', 'effective_price', 'in_stock', 'sku',
                  'category', 'is_featured', 'favorite_count', 'view_count', 'review_count', 'average_rating',
                  'created_at', 'updated_at')


class SEOMetadataSerializer(serializers.Serializer):
    meta_title = serializers.CharField()
    meta_description = serializers.CharField()
    meta_keywords = serializers.CharField(allow_blank=True)
    canonical_url = serializers.URLField()
    og_title = serializers.CharField()
    og_description = serializers.CharField()
    og_image = serializers.URLField(allow_null=True)
    open_graph = serializers.DictField()
    twitter = serializers.DictField()
    structured_data = serializers.DictField()
    robots_index = serializers.BooleanField()
    robots_follow = serializers.BooleanField()


class ProductDetailSerializer(ProductSerializer):
    seo = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = (*ProductSerializer.Meta.fields, 'description', 'seo')

    @extend_schema_field(SEOMetadataSerializer)
    def get_seo(self, product):
        return metadata(product, self.context['request'])

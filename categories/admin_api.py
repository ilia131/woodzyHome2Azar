from django.db import connection, transaction
from rest_framework import serializers

from core.admin_api import CatalogAdminViewSet
from .models import Category
from .services import lock_hierarchy


class CategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description', 'image', 'parent', 'is_active', 'created_at')

    def validate_slug(self, value):
        if value in {'suggested', 'popular'}:
            raise serializers.ValidationError('This slug is reserved.')
        return value


class AdminCategories(CatalogAdminViewSet):
    queryset = Category.objects.all()
    serializer_class = CategoryWriteSerializer
    search_fields = ('name', 'slug')
    ordering_fields = ('id', 'name', 'created_at')

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        lock_hierarchy(connection)
        return super().partial_update(request, *args, **kwargs)

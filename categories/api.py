from rest_framework import generics, serializers

from .models import Category
from .selectors import public_categories


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'description', 'image', 'parent', 'created_at')


class CategoryList(generics.ListAPIView):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return public_categories()


class CategoryDetail(generics.RetrieveAPIView):
    serializer_class = CategorySerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return public_categories()


class CategoryChildren(CategoryList):
    def get_queryset(self):
        from django.shortcuts import get_object_or_404

        queryset = super().get_queryset()
        return queryset.filter(parent=get_object_or_404(queryset, slug=self.kwargs['slug']))

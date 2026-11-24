from django.utils.cache import add_never_cache_headers
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from categories.api import CategorySerializer
from categories.models import Category
from products.models import Product
from products.serializers import ProductSerializer
from .services import popular_products, recommended_categories, recommended_products, similar_products


class ProductFeed(generics.ListAPIView):
    queryset = Product.objects.none()
    serializer_class = ProductSerializer


class PrivateFeed:
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response


@extend_schema_view(get=extend_schema(description='Visible products ranked by weighted favorites and product views.'))
class Popular(ProductFeed):
    def get_queryset(self):
        return popular_products()


@extend_schema_view(get=extend_schema(description=(
    'Personalized catalog suggestions based on saved favorites and sufficient recent views. '
    'Guests and accounts without enough signals receive popular products.')))
class Recommended(PrivateFeed, ProductFeed):
    def get_queryset(self):
        return recommended_products(self.request.user)


@extend_schema_view(get=extend_schema(description=(
    'Suggest other products in categories represented in the authenticated caller’s favorites.')))
class FromFavorites(PrivateFeed, ProductFeed):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return recommended_products(self.request.user, favorites_only=True)


@extend_schema_view(get=extend_schema(description='Find products with related categories and similar title or description.'))
class Similar(ProductFeed):
    def get_queryset(self):
        return similar_products(self.kwargs['slug'])


@extend_schema_view(get=extend_schema(description='Find related products and prioritize recently added items.'))
class Related(ProductFeed):
    def get_queryset(self):
        return similar_products(self.kwargs['slug'], related=True)


@extend_schema_view(get=extend_schema(description=(
    'List visible categories containing active products, ranked by activity and any available personal affinities.')))
class SuggestedCategories(PrivateFeed, generics.ListAPIView):
    queryset = Category.objects.none()
    serializer_class = CategorySerializer

    def get_queryset(self):
        return recommended_categories(self.request.user)

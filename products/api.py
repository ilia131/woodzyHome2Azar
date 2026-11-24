from django.conf import settings
from django_filters import rest_framework as filters
from rest_framework import generics
from rest_framework.response import Response

from analytics.services import COOKIE_AGE, GUEST_COOKIE, record_view
from categories.selectors import public_categories, visible_category_ids
from recommendations.ranking import catalog_score
from .selectors import public_products
from .serializers import ProductDetailSerializer, ProductSerializer


class StableCatalogOrdering(filters.OrderingFilter):
    def filter(self, queryset, value):
        if not value:
            return queryset
        fields = [self.get_ordering_value(option) for option in value if option]
        if any(field.lstrip('-') == 'catalog_score' for field in fields):
            queryset = catalog_score(queryset)
        return queryset.order_by(*fields, '-pk')


class ProductFilter(filters.FilterSet):
    category = filters.CharFilter(method='filter_category')
    in_stock = filters.BooleanFilter(method='filter_stock')
    featured = filters.BooleanFilter(field_name='is_featured')
    min_price = filters.NumberFilter(field_name='effective_price_sort', lookup_expr='gte', min_value=0)
    max_price = filters.NumberFilter(field_name='effective_price_sort', lookup_expr='lte', min_value=0)
    ordering = StableCatalogOrdering(fields=(
        ('effective_price_sort', 'price'), ('created_at', 'newest'), ('discount_sort', 'discount'),
        ('favorite_count', 'favorites'), ('view_count', 'views'), ('catalog_score', 'score'),
    ))

    def filter_category(self, queryset, name, value):
        category = public_categories().filter(slug=value).first()
        ids = visible_category_ids(category.pk) if category else set()
        return queryset.filter(category_id__in=ids)

    def filter_stock(self, queryset, name, value):
        return queryset.filter(stock__gt=0) if value else queryset.filter(stock=0)


class ProductList(generics.ListAPIView):
    serializer_class = ProductSerializer
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = ProductFilter

    def get_queryset(self):
        return public_products()


class MostViewed(ProductList):
    def get_queryset(self):
        return public_products().order_by('-view_count', '-pk')


class MostFavorited(ProductList):
    def get_queryset(self):
        return public_products().order_by('-favorite_count', '-pk')


class BestDiscounts(ProductList):
    def get_queryset(self):
        return public_products().filter(discount_price__isnull=False).order_by('-discount_sort', '-pk')


class ProductDetail(generics.RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return public_products()

    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()
        guest, recorded = record_view(request, product) if request.method == 'GET' else (None, False)
        if recorded:
            product.view_count += 1
        response = Response(self.get_serializer(product).data)
        if guest and request.get_signed_cookie(GUEST_COOKIE, default=None, max_age=COOKIE_AGE) is None:
            response.set_signed_cookie(GUEST_COOKIE, guest, max_age=COOKIE_AGE, httponly=True,
                                       samesite='Lax', secure=settings.SESSION_COOKIE_SECURE)
        response['Cache-Control'] = 'private, no-store'
        return response

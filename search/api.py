from django.utils.cache import add_never_cache_headers
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.api import ProductList
from products.models import Product
from .models import RecentSearch, SearchTerm
from .selectors import category_suggestions, popular_terms, product_results, product_suggestions, recent_terms
from .serializers import (
    PopularTermSerializer, RecentTermSerializer, SearchQuerySerializer, SuggestionQuerySerializer,
    SuggestionsSerializer,
)
from .services import record_search


class SearchProducts(ProductList):
    queryset = Product.objects.none()
    throttle_scope = 'search'

    def get_queryset(self):
        return product_results(self.phrase)

    @extend_schema(parameters=[SearchQuerySerializer], description=(
        'Search visible products by title, descriptions or category name. Ranked by relevance by default. '
        'Catalog filters and ordering are supported. A successful request for page 1 records the search; '
        'authenticated searches are also added to the caller’s private history.'))
    def get(self, request, *args, **kwargs):
        query = SearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        self.phrase = query.validated_data['q']
        response = self.list(request, *args, **kwargs)
        if request.method == 'GET' and self.paginator.page.number == 1:
            record_search(request.user, self.phrase, bool(response.data['results']))
        add_never_cache_headers(response)
        return response


class Suggestions(generics.GenericAPIView):
    serializer_class = SuggestionsSerializer
    throttle_scope = 'search'

    @extend_schema(parameters=[SuggestionQuerySerializer], description=(
        'Find visible product titles and category names as the user types. '
        'Exact and prefix matches come first. Requests do not update search history.'))
    def get(self, request):
        query = SuggestionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        phrase, limit = query.validated_data['q'], query.validated_data['limit']
        return Response(self.get_serializer({
            'products': product_suggestions(phrase)[:limit],
            'categories': category_suggestions(phrase)[:limit],
        }).data)


class Popular(generics.ListAPIView):
    queryset = SearchTerm.objects.none()
    serializer_class = PopularTermSerializer
    throttle_scope = 'search'

    def get_queryset(self):
        return popular_terms()

    @extend_schema(description='List submitted phrases that still occur in visible catalog titles or category names.')
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class Recent(generics.ListAPIView):
    queryset = RecentSearch.objects.none()
    serializer_class = RecentTermSerializer
    permission_classes = [IsAuthenticated]
    throttle_scope = 'search'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return recent_terms(self.request.user)

    @extend_schema(description='List the authenticated caller’s recent normalized search phrases, newest first.')
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response

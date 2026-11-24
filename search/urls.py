from django.urls import path

from .api import Popular, Recent, SearchProducts, Suggestions

urlpatterns = [
    path('suggestions/', Suggestions.as_view(), name='search-suggestions'),
    path('products/', SearchProducts.as_view(), name='search-products'),
    path('popular/', Popular.as_view(), name='search-popular'),
    path('recent/', Recent.as_view(), name='search-recent'),
]

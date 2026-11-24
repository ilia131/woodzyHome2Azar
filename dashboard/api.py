from django.utils.cache import add_never_cache_headers
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from analytics.models import ProductView
from favorites.selectors import favorite_products
from notifications.models import Notification
from products.models import Product
from products.serializers import ProductSerializer
from reviews.models import Review
from reviews.selectors import owned_reviews
from reviews.serializers import OwnedReviewSerializer
from search.models import RecentSearch
from search.selectors import recent_terms
from search.serializers import RecentTermSerializer
from .selectors import notifications_feed, product_view_history
from .serializers import NotificationSerializer, OverviewSerializer, ProductViewSerializer
from .services import overview


class PrivateDashboardResponse:
    permission_classes = [IsAuthenticated]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        add_never_cache_headers(response)
        return response


@extend_schema_view(get=extend_schema(description=(
    'Return the caller’s profile, total saved favorites, review count and average across all moderation states, '
    'and notification counts. The review average is null when the caller has no reviews.')))
class DashboardOverview(PrivateDashboardResponse, generics.RetrieveAPIView):
    serializer_class = OverviewSerializer

    def get_object(self):
        return overview(self.request.user)


class DashboardList(PrivateDashboardResponse, generics.ListAPIView):
    selector = None

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return self.selector(self.request.user)


@extend_schema_view(get=extend_schema(description='List the caller’s favorites that are visible in the catalog.'))
class DashboardFavorites(DashboardList):
    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    selector = staticmethod(favorite_products)


@extend_schema_view(get=extend_schema(description='List the caller’s reviews, including pending and rejected reviews.'))
class DashboardReviews(DashboardList):
    queryset = Review.objects.none()
    serializer_class = OwnedReviewSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_reviews(self.request.user, with_replies=True)


@extend_schema_view(get=extend_schema(description='List the caller’s recent normalized search phrases.'))
class DashboardSearches(DashboardList):
    queryset = RecentSearch.objects.none()
    serializer_class = RecentTermSerializer
    selector = staticmethod(recent_terms)


@extend_schema_view(get=extend_schema(description=(
    'List recorded signed-in views of publicly visible products, newest first. '
    'Guest activity is excluded and repeated views may be deduplicated when recorded.')))
class DashboardViews(DashboardList):
    queryset = ProductView.objects.none()
    serializer_class = ProductViewSerializer
    selector = staticmethod(product_view_history)


@extend_schema_view(get=extend_schema(description='List the caller’s notifications and their read states, newest first.'))
class DashboardNotifications(DashboardList):
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer
    selector = staticmethod(notifications_feed)

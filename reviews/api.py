from django.utils.cache import add_never_cache_headers
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response

from core.admin_api import StaffModelPermissions
from .models import Review, ReviewReply
from .selectors import public_reviews, review_feed
from .serializers import (
    AdminReviewSerializer, ErrorSerializer, ModerationSerializer, OwnedReviewSerializer, PublicReviewSerializer,
    ReplySerializer, ReplyWriteSerializer, ReviewWriteSerializer,
)
from .services import create_review, delete_review, edit_review, moderate_review, reply_to_review


class StableReviewOrdering(filters.OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        return (*ordering, '-pk')


class ReviewListMixin:
    filter_backends = [DjangoFilterBackend, StableReviewOrdering]
    ordering_fields = ('created_at', 'rating')
    ordering = ('-created_at',)


@extend_schema_view(get=extend_schema(description='List only approved reviews for a publicly visible product.'))
class ProductReviews(ReviewListMixin, generics.ListAPIView):
    queryset = Review.objects.none()
    serializer_class = PublicReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filterset_fields = ('rating',)

    def get_queryset(self):
        return public_reviews(self.kwargs['product_id'])

    def get_throttles(self):
        if self.request.method == 'POST':
            self.throttle_scope = 'review'
        return super().get_throttles()

    @extend_schema(
        request=ReviewWriteSerializer,
        responses={201: OwnedReviewSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
        description='Submit a review for moderation. Each account may have one review per product.',
    )
    def post(self, request, product_id):
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = create_review(request.user, product_id, serializer.validated_data)
        response = Response(OwnedReviewSerializer(review).data, status=status.HTTP_201_CREATED)
        add_never_cache_headers(response)
        return response


class OwnerReview(generics.GenericAPIView):
    queryset = Review.objects.none()
    serializer_class = OwnedReviewSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ReviewWriteSerializer, responses={200: OwnedReviewSerializer, 404: ErrorSerializer},
                   description='Update your own review. A content change sends it back for moderation.')
    def patch(self, request, pk):
        serializer = ReviewWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        review = edit_review(request.user, pk, serializer.validated_data)
        response = Response(self.get_serializer(review).data)
        add_never_cache_headers(response)
        return response

    @extend_schema(responses={204: None, 404: ErrorSerializer}, description='Delete your own review.')
    def delete(self, request, pk):
        delete_review(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(get=extend_schema(description='List reviews in all moderation states for authorized staff.'))
class AdminReviews(ReviewListMixin, generics.ListAPIView):
    queryset = Review.objects.none()
    serializer_class = AdminReviewSerializer
    permission_classes = [StaffModelPermissions]
    filterset_fields = ('product', 'rating', 'is_approved')

    def get_queryset(self):
        return review_feed()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response


@extend_schema_view(get=extend_schema(description='Read a review and its replies for authorized staff.'))
class AdminReview(generics.RetrieveAPIView):
    queryset = Review.objects.none()
    serializer_class = AdminReviewSerializer
    permission_classes = [StaffModelPermissions]

    def get_queryset(self):
        return review_feed()

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response

    @extend_schema(request=ModerationSerializer, responses={200: AdminReviewSerializer, 404: ErrorSerializer},
                   description='Approve or reject a review. Requires change_review permission and creates an audit log.')
    def patch(self, request, pk):
        serializer = ModerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = moderate_review(request.user, pk, serializer.validated_data['is_approved'])
        response = Response(self.get_serializer(review).data)
        add_never_cache_headers(response)
        return response


class AdminReply(generics.GenericAPIView):
    queryset = ReviewReply.objects.none()
    serializer_class = ReplySerializer
    permission_classes = [StaffModelPermissions]

    @extend_schema(request=ReplyWriteSerializer, responses={201: ReplySerializer, 404: ErrorSerializer},
                   description='Post a staff reply. Requires add_reviewreply permission and creates an audit log.')
    def post(self, request, review_id):
        serializer = ReplyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply = reply_to_review(request.user, review_id, serializer.validated_data['comment'])
        response = Response(self.get_serializer(reply).data, status=status.HTTP_201_CREATED)
        add_never_cache_headers(response)
        return response

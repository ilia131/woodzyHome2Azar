from drf_spectacular.utils import extend_schema
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.selectors import public_products
from products.serializers import ProductSerializer
from .selectors import favorite_products
from .services import add_favorite, remove_favorite


class Favorites(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return public_products().none()
        return favorite_products(self.request.user)


class FavoriteStatus(serializers.Serializer):
    favorited = serializers.BooleanField()


class FavoriteDetail(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FavoriteStatus

    @extend_schema(request=None, responses={200: FavoriteStatus, 201: FavoriteStatus})
    def post(self, request, product_id):
        product = get_object_or_404(public_products(), pk=product_id)
        created = add_favorite(request.user, product)
        return Response({'favorited': True}, status=201 if created else 200)

    @extend_schema(responses={204: None})
    def delete(self, request, product_id):
        remove_favorite(request.user, product_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

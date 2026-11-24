from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404

from core.admin_api import CatalogAdminViewSet
from .models import User
from .services import change_customer_activity


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'phone', 'first_name', 'last_name', 'email', 'date_joined', 'is_active', 'phone_verified_at')


class CustomerActivitySerializer(serializers.Serializer):
    is_active = serializers.BooleanField()

    def validate(self, attrs):
        if 'is_active' not in self.initial_data:
            raise serializers.ValidationError({'is_active': 'Provide an explicit account status.'})
        return attrs


class AdminCustomers(CatalogAdminViewSet):
    queryset = User.objects.none()
    serializer_class = CustomerSerializer
    filterset_fields = ('is_active',)
    search_fields = ('phone', 'email', 'first_name', 'last_name')
    ordering_fields = ('id', 'date_joined')
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        # EXISTS-style checks avoid a nullable join when the update locks the account.

        privileged = User.objects.filter(pk=OuterRef('pk'))
        return User.objects.filter(is_staff=False, is_superuser=False).filter(
            ~Exists(privileged.filter(groups__isnull=False)), ~Exists(privileged.filter(user_permissions__isnull=False)),
        ).order_by('pk')

    @extend_schema(request=CustomerActivitySerializer, responses=CustomerSerializer)
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):

        data = CustomerActivitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        account = get_object_or_404(self.get_queryset().select_for_update(), pk=kwargs['pk'])
        account = change_customer_activity(request.user, account, data.validated_data['is_active'])
        return Response(self.get_serializer(account).data)

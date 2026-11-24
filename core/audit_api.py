from rest_framework import serializers, viewsets
from django_filters.rest_framework import DjangoFilterBackend

from .admin_api import StaffModelPermissions
from .models import AuditLog


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ('id', 'actor', 'action', 'model_label', 'object_id', 'created_at')


class AdminAuditLog(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.order_by('-created_at', '-pk')
    permission_classes = [StaffModelPermissions]
    serializer_class = AuditSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ('actor', 'action', 'model_label', 'object_id')

from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from rest_framework import filters, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import DjangoModelPermissions

from .models import AuditLog


class StaffModelPermissions(DjangoModelPermissions):
    perms_map = {**DjangoModelPermissions.perms_map, 'GET': ['%(app_label)s.view_%(model_name)s'],
                 'HEAD': ['%(app_label)s.view_%(model_name)s']}

    def has_permission(self, request, view):
        return request.user.is_staff and super().has_permission(request, view)


def audit(actor, action, obj, *, metadata=None):
    AuditLog.objects.create(actor=actor, action=action, model_label=obj._meta.label_lower,
                            object_id=str(obj.pk), metadata={} if metadata is None else metadata)


class CatalogAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [StaffModelPermissions]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    ordering = ('pk',)
    ordering_fields = ('id',)
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'partial_update':
            return queryset.select_for_update(of=('self',))
        return queryset

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer):
        self.save_and_audit(serializer, 'create')

    def perform_update(self, serializer):
        self.save_and_audit(serializer, 'update')

    def save_and_audit(self, serializer, action):
        try:
            obj = serializer.save()
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict if hasattr(error, 'message_dict') else error.messages) from error
        audit(self.request.user, action, obj)

    @transaction.atomic
    def perform_destroy(self, instance):
        audit(self.request.user, 'delete', instance)
        try:
            instance.delete()
        except ProtectedError as error:
            raise ValidationError('Remove dependent records before deleting this record.') from error

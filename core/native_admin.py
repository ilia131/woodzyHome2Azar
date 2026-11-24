from django.contrib import admin
from django.db import transaction
from .admin_api import audit


class AuditedAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit(request.user, 'update' if change else 'create', obj)

    def delete_model(self, request, obj):
        audit(request.user, 'delete', obj)
        super().delete_model(request, obj)

    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for obj in queryset:
            audit(request.user, 'delete', obj)
        super().delete_queryset(request, queryset)

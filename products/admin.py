from django import forms
from django.contrib import admin
from django.db import transaction
from orders.inventory import record_initial_stock

from core.native_admin import AuditedAdmin
from .admin_api import RESERVED_SLUGS
from .models import Product, ProductChange, ProductImage


class ProductForm(forms.ModelForm):
    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if slug in RESERVED_SLUGS:
            raise forms.ValidationError('This slug is reserved.')
        return slug


@admin.register(Product)
class ProductAdmin(AuditedAdmin):
    form = ProductForm
    list_display = ('title', 'sku', 'price', 'discount_price', 'stock', 'is_active')
    list_filter = ('is_active', 'is_featured', 'category')
    search_fields = ('title', 'sku')
    prepopulated_fields = {'slug': ('title',)}

    def get_readonly_fields(self, request, obj=None):
        return ('slug', 'stock') if obj else ()

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            obj.stock = Product.objects.select_for_update().values_list('stock', flat=True).get(pk=obj.pk)
        super().save_model(request, obj, form, change)
        if not change:
            record_initial_stock(obj, request.user)

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj else super().get_prepopulated_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductChange)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'price', 'discount_price', 'stock', 'created_at')
    readonly_fields = list_display

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ProductImage, AuditedAdmin)

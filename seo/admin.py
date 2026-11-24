from django import forms
from django.contrib import admin
from core.native_admin import AuditedAdmin
from .models import ProductSEO


class SEOForm(forms.ModelForm):
    def clean_structured_data(self):
        data = self.cleaned_data['structured_data']
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise forms.ValidationError('Use a JSON object.')
        return data


@admin.register(ProductSEO)
class SEOAdmin(AuditedAdmin):
    form = SEOForm
    search_fields = ('product__title', 'meta_title')

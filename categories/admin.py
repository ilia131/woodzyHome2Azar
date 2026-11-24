from django.contrib import admin
from django import forms
from core.native_admin import AuditedAdmin
from .models import Category


class CategoryForm(forms.ModelForm):
    def clean_slug(self):
        slug = self.cleaned_data['slug']
        if slug in {'suggested', 'popular'}:
            raise forms.ValidationError('This slug is reserved.')
        return slug


@admin.register(Category)
class CategoryAdmin(AuditedAdmin):
    form = CategoryForm
    search_fields = ('name', 'slug')
    list_display = ('name', 'parent', 'is_active')

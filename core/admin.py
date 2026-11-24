from django.contrib import admin

from .models import ContactMessage, NewsletterSubscription


@admin.register(ContactMessage)
class ContactInbox(admin.ModelAdmin):
    list_display = ('id', 'name', 'created_at')
    readonly_fields = ('name', 'email', 'message', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(NewsletterSubscription)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ('id', 'email', 'active', 'updated_at')
    list_filter = ('active',)
    readonly_fields = ('email', 'active', 'updated_at')

    def has_add_permission(self, request):
        return False

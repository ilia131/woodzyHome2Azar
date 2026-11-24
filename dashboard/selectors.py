from analytics.models import ProductView
from analytics.services import account_visitor_key
from notifications.models import Notification
from products.selectors import visible_products


def owned_notifications(user):
    return Notification.objects.filter(user=user)


def notifications_feed(user):
    return owned_notifications(user).order_by('-created_at', '-pk')


def product_view_history(user):
    visible = visible_products().order_by().values('pk')
    return ProductView.objects.filter(
        authenticated=True, visitor_key=account_visitor_key(user.pk), product_id__in=visible,
    ).select_related('product').only(
        'id', 'created_at', 'product__id', 'product__slug', 'product__title', 'product__main_image',
    ).order_by('-created_at', '-pk')

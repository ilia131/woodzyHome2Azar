import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.crypto import salted_hmac
from redis.exceptions import RedisError

from .models import ProductView

logger = logging.getLogger(__name__)
VIEW_WINDOW = 30 * 60
GUEST_COOKIE = 'aksoria_visitor'
COOKIE_AGE = 30 * 24 * 60 * 60


def visitor_key(identity):
    return salted_hmac('catalog-visitor', identity, algorithm='sha256').hexdigest()


def account_visitor_key(user_id):
    return visitor_key(f'user:{user_id}')


def record_view(request, product):
    authenticated = request.user.is_authenticated
    guest = None
    if authenticated:
        visitor = account_visitor_key(request.user.pk)
    else:
        guest = request.get_signed_cookie(GUEST_COOKIE, default=None, max_age=COOKIE_AGE)
        if not guest:
            # Use a coarse deduplication key until the client receives its first signed cookie.
            guest = salted_hmac('catalog-guest', f"{request.META.get('REMOTE_ADDR', '')}:"
                                f"{request.META.get('HTTP_USER_AGENT', '')[:512]}", algorithm='sha256').hexdigest()
        visitor = visitor_key(f'guest:{guest}')
    key = f'catalog:view:{product.pk}:{visitor}'
    try:
        acquired = cache.add(key, '1', VIEW_WINDOW)
    except RedisError:
        logger.exception('Could not deduplicate catalog view')
        return guest, False
    if acquired:
        ProductView.objects.create(product=product, visitor_key=visitor, authenticated=authenticated)
    return guest, acquired


def view_metrics(product):
    now = timezone.now()
    metrics = ProductView.objects.filter(product=product).aggregate(
        total=Count('pk'), signed_in=Count('pk', filter=Q(authenticated=True)),
        guest=Count('pk', filter=Q(authenticated=False)),
        unique=Count('visitor_key', distinct=True),
        daily=Count('pk', filter=Q(created_at__gte=now - timedelta(days=1))),
        weekly=Count('pk', filter=Q(created_at__gte=now - timedelta(days=7))),
        monthly=Count('pk', filter=Q(created_at__gte=now - timedelta(days=30))),
        last_view_at=Max('created_at'),
    )
    metrics["authenticated"] = metrics.pop("signed_in")
    return metrics

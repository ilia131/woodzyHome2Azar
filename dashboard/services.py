from django.db.models import Avg, Count, Q

from favorites.selectors import owned_favorites
from reviews.selectors import owned_reviews
from .selectors import owned_notifications


def overview(user):
    reviews = owned_reviews(user).aggregate(count=Count('pk'), average_rating=Avg('rating'))
    notifications = owned_notifications(user).aggregate(
        count=Count('pk'), unread_count=Count('pk', filter=Q(read_at__isnull=True)),
    )
    return {
        'profile': user,
        'favorite_count': owned_favorites(user).count(),
        'reviews': reviews,
        'notifications': notifications,
    }

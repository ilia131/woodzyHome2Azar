from .models import Favorite


def add_favorite(user, product):
    return Favorite.objects.get_or_create(user=user, product=product)[1]


def remove_favorite(user, product_id):
    Favorite.objects.filter(user=user, product_id=product_id).delete()

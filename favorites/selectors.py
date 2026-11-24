from products.selectors import public_products

from .models import Favorite


def owned_favorites(user):
    return Favorite.objects.filter(user=user)


def favorite_products(user):
    return public_products().filter(favorites__user=user).order_by('-favorites__created_at', '-pk')

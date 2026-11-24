from django.contrib.postgres.search import TrigramSimilarity
from django.db import connection
from django.db.models import Count, Exists, IntegerField, Max, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404

from analytics.models import ProductView
from analytics.services import account_visitor_key
from categories.selectors import public_categories, visible_category_ids
from favorites.models import Favorite
from products.selectors import public_products, visible_products


def visible_seed(slug):
    return get_object_or_404(
        visible_products().select_related('category').only(
            'id', 'category__parent_id', 'search_title', 'search_text',
        ), slug=slug,
    )


def related_candidates(seed):
    family = visible_category_ids(seed.category.parent_id or seed.category_id)
    group = Q(category_id__in=family)
    products = public_products().exclude(pk=seed.pk)
    if connection.vendor != 'postgresql':
        return products.filter(group).alias(title_similarity=Value(0.0), text_similarity=Value(0.0))
    queryset = products.alias(
        title_similarity=TrigramSimilarity('search_title', Value(seed.search_title)),
        text_similarity=TrigramSimilarity('search_text', Value(seed.search_text[:500])),
    )
    return queryset.filter(group | Q(search_title__trigram_similar=seed.search_title) |
                           Q(search_text__trigram_similar=seed.search_text[:500]))


def favorite_seeds(user, limit):
    visible = visible_products().order_by().values('pk')
    return list(Favorite.objects.filter(user=user, product_id__in=visible)
                .order_by('-created_at', '-pk').values_list('product_id', 'product__category_id')[:limit])


def viewed_seeds(user, since, limit):
    visible = visible_products().order_by().values('pk')
    return list(ProductView.objects.filter(
        authenticated=True, visitor_key=account_visitor_key(user.pk), created_at__gte=since, product_id__in=visible,
    ).values('product_id', 'product__category_id').annotate(last_seen=Max('created_at'))
      .order_by('-last_seen', '-product_id').values_list('product_id', 'product__category_id')[:limit])


def user_favorites(user):
    return Favorite.objects.filter(user=user, product_id=OuterRef('pk'))


def suggested_categories():
    products = visible_products().filter(category_id=OuterRef('pk')).order_by()
    category_views = ProductView.objects.filter(product__category_id=OuterRef('pk'), product__is_active=True)
    category_favorites = Favorite.objects.filter(product__category_id=OuterRef('pk'), product__is_active=True)

    def count(events):
        totals = events.order_by().values('product__category_id').annotate(total=Count('pk')).values('total')
        return Coalesce(Subquery(totals, output_field=IntegerField()), 0)

    return public_categories().filter(Exists(products)).alias(
        view_count=count(category_views), favorite_count=count(category_favorites),
    )

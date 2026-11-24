from django.db.models import Avg, Count, ExpressionWrapper, FloatField, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Cast, Coalesce

from analytics.models import ProductView
from categories.selectors import visible_category_ids
from favorites.models import Favorite

from .models import Product


def related_count(model):
    counts = model.objects.filter(product_id=OuterRef('pk')).order_by().values('product_id')
    return Coalesce(Subquery(counts.annotate(total=Count('pk')).values('total'), output_field=IntegerField()), 0)


def visible_products():
    return Product.objects.filter(is_active=True, category_id__in=visible_category_ids())


def public_products():
    return visible_products().select_related(
        'category', 'seo').prefetch_related('gallery').annotate(
            effective_price_sort=Coalesce('discount_price', 'price'),
            discount_sort=ExpressionWrapper(
                100.0 * (1.0 - Cast(Coalesce('discount_price', 'price'), FloatField()) / Cast('price', FloatField())),
                output_field=FloatField()),
            favorite_count=related_count(Favorite),
            view_count=related_count(ProductView),
            review_count=Count('reviews', filter=Q(reviews__is_approved=True)),
            average_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
        ).order_by('-created_at', '-pk')

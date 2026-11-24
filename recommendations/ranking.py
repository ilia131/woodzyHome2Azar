from datetime import timedelta

from django.db.models import Case, F, FloatField, Value, When
from django.db.models.functions import Cast
from django.utils import timezone

from .models import RankingWeights


def popularity_score(weights=None):
    if weights is None:
        weights = RankingWeights.objects.first() or RankingWeights()
    return F('view_count') * weights.views + F('favorite_count') * weights.favorites


def rank_by_popularity(queryset):
    return queryset.alias(popularity=popularity_score()).order_by('-popularity', '-created_at', '-pk')

def catalog_score(queryset):
    weights = RankingWeights.objects.first() or RankingWeights()
    recent = timezone.now() - timedelta(days=30)
    score = (popularity_score(weights)
             + F('discount_sort') * weights.discount / 100.0
             + Value(float(weights.affordability)) / (1.0 + Cast('effective_price_sort', FloatField()))
             + Case(When(created_at__gte=recent, then=weights.freshness), default=0)
             + Case(When(is_featured=True, then=weights.featured), default=0))
    return queryset.alias(catalog_score=score)

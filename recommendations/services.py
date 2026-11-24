from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Case, Exists, F, Value, When
from django.utils import timezone

from products.selectors import public_products
from .models import RecommendationPolicy
from .ranking import popularity_score, rank_by_popularity
from .selectors import (
    favorite_seeds, related_candidates, suggested_categories, user_favorites, viewed_seeds, visible_seed,
)


@dataclass(frozen=True)
class RecommendationOptions:
    favorite_weight: int = 5
    view_weight: int = 1
    category_weight: int = 5
    title_weight: float = 3.0
    description_weight: float = 2.0
    history_days: int = 30
    min_viewed_products: int = 2
    seed_limit: int = 20


def options(overrides=None):
    if overrides is None:
        overrides = RecommendationPolicy.objects.values_list('overrides', flat=True).first() or {}
    defaults = getattr(settings, 'RECOMMENDATION_OPTIONS', {})
    return RecommendationOptions(**{**defaults, **overrides})


def category_affinity(favorites, views, config):
    scores = Counter()
    for seeds, weight in ((favorites, config.favorite_weight), (views, config.view_weight)):
        for _, category in seeds:
            scores[category] += weight
    return {category: score for category, score in scores.items() if score > 0}


def affinity_expression(scores, field):
    return Case(*(When(**{field: category}, then=Value(score)) for category, score in scores.items()), default=0)


def profile(user, config, *, favorites_only=False):
    if not user.is_authenticated:
        return {}, []
    favorites = favorite_seeds(user, config.seed_limit)
    views = []
    if not favorites_only:
        since = timezone.now() - timedelta(days=config.history_days)
        recent = viewed_seeds(user, since, config.seed_limit)
        if len(recent) >= config.min_viewed_products:
            views = recent
    return category_affinity(favorites, views, config), [product for product, _ in views]


def popular_products():
    return rank_by_popularity(public_products())


def recommended_products(user, *, favorites_only=False):
    if not user.is_authenticated and not favorites_only:
        return popular_products()
    config = options()
    scores, seen = profile(user, config, favorites_only=favorites_only)
    if not scores:
        return public_products().none() if favorites_only else popular_products()
    queryset = public_products().filter(~Exists(user_favorites(user))).exclude(pk__in=seen)
    if favorites_only:
        queryset = queryset.filter(category_id__in=scores)
    return queryset.alias(
        preference=affinity_expression(scores, 'category_id'), popularity=popularity_score(),
    ).order_by('-preference', '-popularity', '-created_at', '-pk')


def similar_products(slug, *, related=False):
    seed = visible_seed(slug)
    config = options()
    queryset = related_candidates(seed).alias(
        resemblance=Case(When(category_id=seed.category_id, then=config.category_weight), default=0)
        + F('title_similarity') * config.title_weight + F('text_similarity') * config.description_weight,
        popularity=popularity_score(),
    )
    if related:
        return queryset.order_by('-created_at', '-resemblance', '-popularity', '-pk')
    return queryset.order_by('-resemblance', '-popularity', '-created_at', '-pk')


def recommended_categories(user):
    scores, _ = profile(user, options()) if user.is_authenticated else ({}, [])
    queryset = suggested_categories().alias(popularity=popularity_score())
    ordering = ('-popularity', 'name', 'pk')
    if scores:
        queryset = queryset.alias(preference=affinity_expression(scores, 'pk'))
        ordering = ('-preference', *ordering)
    return queryset.order_by(*ordering)

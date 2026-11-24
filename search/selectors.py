from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector, TrigramWordSimilarity
from django.db import connection
from django.db.models import Case, Exists, OuterRef, Q, Value, When
from django.db.models.functions import Greatest, StrIndex

from categories.models import Category
from categories.selectors import public_categories
from products.models import Product
from products.selectors import public_products, visible_products
from .models import RecentSearch, SearchTerm


def product_results(term):
    query = public_products()
    products = Product.objects.all()
    categories = Category.objects.all()
    product_matches = Q(search_text__contains=term)
    category_matches = Q(search_name__contains=term)
    full_text_rank = Value(0.0)
    similarity = Value(0.0)
    if connection.vendor == 'postgresql':
        vector = SearchVector('search_text', config='simple')
        category_vector = SearchVector('category__search_name', config='simple')
        words = SearchQuery(term, config='simple')
        products = products.alias(document=vector)
        categories = categories.alias(document=SearchVector('search_name', config='simple'))
        product_matches |= Q(document=words)
        category_matches |= Q(document=words)
        full_text_rank = Greatest(SearchRank(vector, words), SearchRank(category_vector, words))
        if len(term) >= 3:
            product_matches |= Q(search_title__trigram_word_similar=term)
            category_matches |= Q(search_name__trigram_word_similar=term)
            similarity = Greatest(TrigramWordSimilarity(term, 'search_title'),
                                  TrigramWordSimilarity(term, 'category__search_name'))
    # Choose candidates per table so the GIN predicates can use their own indexes.
    category_ids = categories.filter(category_matches).order_by().values('pk')
    by_category = Product.objects.filter(category_id__in=category_ids).order_by().values('pk')
    by_text = products.filter(product_matches).order_by().values('pk')
    return query.filter(pk__in=by_text.union(by_category, all=True)).alias(
        match_priority=Case(
            When(search_title=term, then=5),
            When(search_title__startswith=term, then=4),
            When(search_title__contains=term, then=3),
            When(category__search_name__contains=term, then=2),
            When(search_text__contains=term, then=1),
            default=0,
        ),
        text_rank=full_text_rank,
        similarity=similarity,
    ).order_by('-match_priority', '-text_rank', '-similarity', '-pk')


def suggestions(queryset, field, term):
    matches = Q(**{f'{field}__contains': term})
    similarity = Value(0.0)
    if connection.vendor == 'postgresql' and len(term) >= 3:
        matches |= Q(**{f'{field}__trigram_word_similar': term})
        similarity = TrigramWordSimilarity(term, field)
    return queryset.filter(matches).alias(
        priority=Case(
            When(**{field: term}, then=3),
            When(**{f'{field}__startswith': term}, then=2),
            When(**{f'{field}__contains': term}, then=1),
            default=0,
        ), similarity=similarity,
    ).order_by('-priority', '-similarity', field, 'pk')


def product_suggestions(term):
    return suggestions(visible_products(), 'search_title', term).only('id', 'title', 'slug')


def category_suggestions(term):
    return suggestions(public_categories(), 'search_name', term).only('id', 'name', 'slug')


def matches_public_label(term):
    return (visible_products().filter(search_title__contains=term).exists()
            or public_categories().filter(search_name__contains=term).exists())


def popular_terms():
    # Recheck visibility before publishing a phrase from historical searches.
    titles = visible_products().alias(position=StrIndex('search_title', OuterRef('term'))).filter(position__gt=0)
    categories = public_categories().alias(position=StrIndex('search_name', OuterRef('term'))).filter(position__gt=0)
    return SearchTerm.objects.filter(count__gt=0).filter(
        Exists(titles) | Exists(categories),
    ).order_by('-count', 'term')


def recent_terms(user):
    return RecentSearch.objects.filter(user=user).select_related('term').order_by('-updated_at', '-pk')

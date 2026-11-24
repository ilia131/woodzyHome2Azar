from django.db import transaction
from django.db.models import F

from .models import RecentSearch, SearchTerm
from .selectors import matches_public_label


def record_search(user, phrase, has_results):
    publishable = has_results and matches_public_label(phrase)
    if publishable or user.is_authenticated:
        with transaction.atomic():
            term, _ = SearchTerm.objects.get_or_create(term=phrase)
            if publishable:
                SearchTerm.objects.filter(pk=term.pk).update(count=F('count') + 1)
            if user.is_authenticated:
                RecentSearch.objects.update_or_create(user=user, term=term, defaults={})

from django.conf import settings
from django.db import models


class SearchTerm(models.Model):
    term = models.CharField(max_length=120, unique=True)
    count = models.PositiveBigIntegerField(default=0, db_index=True)


class RecentSearch(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    term = models.ForeignKey(SearchTerm, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'term'], name='one_recent_term_per_user')]
        indexes = [models.Index(fields=['user', '-updated_at'])]

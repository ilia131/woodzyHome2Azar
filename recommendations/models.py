from django.db import models
from django.core.validators import MaxValueValidator


class RankingWeights(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    views = models.PositiveSmallIntegerField(default=2, validators=[MaxValueValidator(100)])
    favorites = models.PositiveSmallIntegerField(default=8, validators=[MaxValueValidator(100)])
    sales = models.PositiveSmallIntegerField(default=15, validators=[MaxValueValidator(100)])
    discount = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(100)])
    affordability = models.PositiveSmallIntegerField(default=1, validators=[MaxValueValidator(100)])
    freshness = models.PositiveSmallIntegerField(default=5, validators=[MaxValueValidator(100)])
    featured = models.PositiveSmallIntegerField(default=5, validators=[MaxValueValidator(100)])

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(singleton=1), name='one_ranking_config')]


class RecommendationPolicy(models.Model):
    singleton = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    # Sparse overrides preserve Django setting defaults for installations that already tune the service.
    overrides = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(singleton=1), name='one_recommendation_policy')]

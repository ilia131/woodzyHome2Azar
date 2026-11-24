from django.db import transaction
from rest_framework import generics, serializers
from rest_framework.response import Response

from core.admin_api import CatalogAdminViewSet, StaffModelPermissions, audit
from .models import RankingWeights, RecommendationPolicy
from .services import options


class RankingWeightsSerializer(serializers.ModelSerializer):
    class Meta:
        model = RankingWeights
        fields = ('id', 'views', 'favorites', 'discount', 'affordability', 'freshness', 'featured')


class AdminRankingWeights(CatalogAdminViewSet):
    queryset = RankingWeights.objects.all()
    serializer_class = RankingWeightsSerializer
    http_method_names = ['get', 'patch', 'head', 'options']


class RecommendationPolicySerializer(serializers.Serializer):
    favorite_weight = serializers.IntegerField(min_value=0, max_value=100)
    view_weight = serializers.IntegerField(min_value=0, max_value=100)
    category_weight = serializers.IntegerField(min_value=0, max_value=100)
    title_weight = serializers.FloatField(min_value=0, max_value=100)
    description_weight = serializers.FloatField(min_value=0, max_value=100)
    history_days = serializers.IntegerField(min_value=1, max_value=365)
    min_viewed_products = serializers.IntegerField(min_value=1, max_value=100)
    seed_limit = serializers.IntegerField(min_value=1, max_value=100)

    def validate(self, attrs):
        effective = options({**self.context['overrides'], **attrs})
        if effective.min_viewed_products > effective.seed_limit:
            raise serializers.ValidationError({'min_viewed_products': 'Must not exceed seed_limit.'})
        return attrs


class AdminRecommendationPolicy(generics.GenericAPIView):
    queryset = RecommendationPolicy.objects.all()
    serializer_class = RecommendationPolicySerializer
    permission_classes = [StaffModelPermissions]

    def get(self, request):
        return Response(self.get_serializer(options()).data)

    @transaction.atomic
    def patch(self, request):
        policy, _ = RecommendationPolicy.objects.select_for_update().get_or_create(singleton=1)
        data = self.get_serializer(data=request.data, partial=True, context={'overrides': policy.overrides})
        data.is_valid(raise_exception=True)
        policy.overrides = {**policy.overrides, **data.validated_data}
        policy.save(update_fields=['overrides'])
        audit(request.user, 'update', policy)
        return Response(self.get_serializer(options(policy.overrides)).data)

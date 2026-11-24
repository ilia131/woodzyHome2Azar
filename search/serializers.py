from rest_framework import serializers

from categories.models import Category
from core.text import normalize
from products.models import Product
from .models import RecentSearch, SearchTerm


class SearchQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=120, help_text='Persian or English search phrase, 2–120 normalized characters.')

    def validate_q(self, value):
        term = normalize(value)
        if not 2 <= len(term) <= 120 or not any(character.isalnum() for character in term):
            raise serializers.ValidationError('Enter 2 to 120 characters including at least one letter or number.')
        return term


class SuggestionQuerySerializer(SearchQuerySerializer):
    limit = serializers.IntegerField(min_value=1, max_value=20, default=8,
                                     help_text='Maximum suggestions per group.')


class ProductSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'title', 'slug')


class CategorySuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name', 'slug')


class SuggestionsSerializer(serializers.Serializer):
    products = ProductSuggestionSerializer(many=True)
    categories = CategorySuggestionSerializer(many=True)


class PopularTermSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchTerm
        fields = ('term', 'count')


class RecentTermSerializer(serializers.ModelSerializer):
    term = serializers.CharField(source='term.term')

    class Meta:
        model = RecentSearch
        fields = ('term', 'updated_at')

from rest_framework import serializers

from accounts.api import ProfileSerializer
from analytics.models import ProductView
from notifications.models import Notification
from products.models import Product


class ReviewSummarySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    average_rating = serializers.FloatField(allow_null=True)


class NotificationSummarySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    unread_count = serializers.IntegerField()


class OverviewSerializer(serializers.Serializer):
    profile = ProfileSerializer()
    favorite_count = serializers.IntegerField(help_text='All saved favorites, including currently hidden products.')
    reviews = ReviewSummarySerializer()
    notifications = NotificationSummarySerializer()


class ProductHistoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'slug', 'title', 'main_image')


class ProductViewSerializer(serializers.ModelSerializer):
    product = ProductHistoryItemSerializer(read_only=True)
    viewed_at = serializers.DateTimeField(source='created_at')

    class Meta:
        model = ProductView
        fields = ('id', 'product', 'viewed_at')


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ('id', 'title', 'body', 'created_at', 'read_at', 'is_read')

    def get_is_read(self, notification) -> bool:
        return notification.read_at is not None

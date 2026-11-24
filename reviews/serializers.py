from rest_framework import serializers

from .models import Review, ReviewReply


class ReviewWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ('rating', 'title', 'comment')


class ReplyWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewReply
        fields = ('comment',)


class ReplySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewReply
        fields = ('id', 'parent', 'comment', 'created_at')


class PublicReviewSerializer(serializers.ModelSerializer):
    replies = ReplySerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = ('id', 'rating', 'title', 'comment', 'created_at', 'updated_at', 'replies')


class OwnedReviewSerializer(PublicReviewSerializer):
    class Meta(PublicReviewSerializer.Meta):
        fields = (*PublicReviewSerializer.Meta.fields, 'product', 'is_approved', 'moderated_at')


class AdminReviewSerializer(OwnedReviewSerializer):
    class Meta(OwnedReviewSerializer.Meta):
        fields = (*OwnedReviewSerializer.Meta.fields, 'user')


class ModerationSerializer(serializers.Serializer):
    is_approved = serializers.BooleanField()

    def validate(self, attrs):
        # HTML form omission must not silently turn into a rejection.
        if 'is_approved' not in self.initial_data:
            raise serializers.ValidationError({'is_approved': 'Provide an explicit moderation decision.'})
        return attrs


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()

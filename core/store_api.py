import uuid

from django.core import signing
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from celery import shared_task

from .store_mail import deliver, enqueue, require_mail
from .models import ContactMessage, NewsletterSubscription


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ('name', 'email', 'message')


class PublicStore(generics.GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class Contact(PublicStore):
    serializer_class = ContactSerializer
    throttle_scope = 'store_contact'

    @extend_schema(responses={201: None})
    def post(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.save()
        return Response(status=201)


class NewsletterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    action = serializers.ChoiceField(choices=['subscribe', 'unsubscribe'])


class NewsletterCodeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=1024)


NEWSLETTER_SALT = 'woodzy.newsletter'


@shared_task(ignore_result=True)
def send_newsletter_code(email, action):
    subscribed = action == 'subscribe'
    record = NewsletterSubscription.objects.filter(email=email).first()
    if not record and subscribed:
        record, _ = NewsletterSubscription.objects.get_or_create(email=email)
    if record and record.active != subscribed:
        token = signing.dumps({'id': record.pk, 'revision': str(record.revision), 'active': subscribed},
                              salt=NEWSLETTER_SALT)
        deliver('WoodzyHome newsletter ' + action, token, email)


class Newsletter(PublicStore):
    serializer_class = NewsletterSerializer
    throttle_scope = 'newsletter'

    @extend_schema(responses={202: None, 503: None})
    def post(self, request):
        require_mail()
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        enqueue(send_newsletter_code, data.validated_data['email'].lower(), data.validated_data['action'])
        return Response(status=202)


class NewsletterConfirm(PublicStore):
    serializer_class = NewsletterCodeSerializer
    throttle_scope = 'newsletter'

    @extend_schema(responses={204: None, 400: None})
    @transaction.atomic
    def post(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            proof = signing.loads(data.validated_data['token'], max_age=86400, salt=NEWSLETTER_SALT)
        except signing.BadSignature as error:
            raise ValidationError({'token': 'Invalid or expired subscription code.'}) from error
        entry = NewsletterSubscription.objects.select_for_update().filter(pk=proof['id']).first()
        if not entry or str(entry.revision) != proof['revision']:
            raise ValidationError({'token': 'Invalid or expired subscription code.'})
        entry.active = proof['active']
        entry.revision = uuid.uuid4()
        entry.save(update_fields=['active', 'revision', 'updated_at'])
        return Response(status=204)

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from core.admin_api import audit
from .models import User, normalize_phone
from .services import blacklist_sessions

from core.store_mail import deliver, enqueue, require_mail, send_transactional_email
from celery import shared_task


def valid_phone(value):
    try:
        return normalize_phone(value)
    except DjangoValidationError as error:
        raise ValidationError(error.messages) from error


class RecoveryToken(PasswordResetTokenGenerator):
    key_salt = 'woodzy.password-recovery'

    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + f':{user.recovery_email}:{user.recovery_revision}:{user.session_version}:{user.is_active}'


recovery_token = RecoveryToken()


class RecoveryRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32, validators=[valid_phone])
    email = serializers.EmailField(max_length=254)


class RecoveryConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32, validators=[valid_phone])
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class EnrollmentSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False, write_only=True)


class EnrollmentConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=1024)


class PublicRecovery(generics.GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = 'recovery'


@shared_task(ignore_result=True)
def send_recovery(phone, email):
    user = User.objects.filter(phone=phone, is_active=True).first()
    if user and user.has_usable_password() and user.recovery_email.lower() == email.lower():
        deliver('WoodzyHome password recovery', recovery_token.make_token(user), user.recovery_email)


class RecoveryRequest(PublicRecovery):
    serializer_class = RecoveryRequestSerializer

    @extend_schema(responses={202: None, 503: None})
    def post(self, request):
        require_mail()
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        enqueue(send_recovery, valid_phone(data.validated_data['phone']), data.validated_data['email'])
        return Response(status=202)


class RecoveryConfirm(PublicRecovery):
    throttle_scope = 'recovery_confirm'
    serializer_class = RecoveryConfirmSerializer

    @extend_schema(responses={204: None, 400: None})
    @transaction.atomic
    def post(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        phone, token, password = (data.validated_data[key] for key in ('phone', 'token', 'password'))
        user = User.objects.select_for_update().filter(phone=valid_phone(phone), is_active=True).first()
        if not user or not user.recovery_email or not recovery_token.check_token(user, token):
            raise ValidationError({'token': 'Invalid or expired recovery code.'})
        try:
            validate_password(password, user)
        except DjangoValidationError as error:
            raise ValidationError({'password': error.messages}) from error
        user.set_password(password)
        user.session_version += 1
        user.save(update_fields=['password', 'session_version'])
        blacklist_sessions(user)
        audit(user, 'password_recovered', user)
        return Response(status=204)


class RecoveryEnroll(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'recovery'
    serializer_class = EnrollmentSerializer

    @extend_schema(responses={202: None, 503: None})
    def post(self, request):
        require_mail()
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        if not request.user.check_password(data.validated_data['password']):
            raise ValidationError({'password': 'Incorrect password.'})
        user = request.user
        address = data.validated_data['email']
        proof = signing.dumps({'user': user.pk, 'email': address, 'session': user.session_version,
                               'credential': recovery_token.make_token(user)}, salt='woodzy.recovery-enrollment')
        enqueue(send_transactional_email, 'WoodzyHome recovery email verification', proof, address)
        return Response(status=202)


class RecoveryEnrollConfirm(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = 'recovery'
    serializer_class = EnrollmentConfirmSerializer

    @extend_schema(responses={204: None, 400: None})
    @transaction.atomic
    def post(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        account = User.objects.select_for_update().get(pk=request.user.pk)
        try:
            proof = signing.loads(data.validated_data['token'], salt='woodzy.recovery-enrollment', max_age=1800)
        except signing.BadSignature as error:
            raise ValidationError({'token': 'Invalid or expired verification code.'}) from error
        if (not account.is_active or proof['user'] != account.pk or proof['session'] != account.session_version
                or not recovery_token.check_token(account, proof['credential'])):
            raise ValidationError({'token': 'Invalid or expired verification code.'})
        account.recovery_email = proof['email']
        account.recovery_revision += 1
        account.save(update_fields=['recovery_email', 'recovery_revision'])
        audit(account, 'recovery_email_verified', account)
        return Response(status=204)

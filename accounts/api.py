from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils.crypto import constant_time_compare
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.utils import get_md5_hash_password
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import User, normalize_phone
from .services import change_password, register, update_profile


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'phone', 'first_name', 'last_name', 'email', 'avatar', 'date_joined', 'is_active', 'phone_verified_at')
        read_only_fields = ('phone', 'date_joined', 'is_active', 'phone_verified_at')


    def update(self, instance, validated_data):
        return update_profile(instance, validated_data)


class RegistrationSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(max_length=32, validators=[normalize_phone])
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    class Meta:
        model = User
        fields = ('id', 'phone', 'password', 'first_name', 'last_name', 'email')

    def validate(self, attrs):
        attrs['phone'] = normalize_phone(attrs['phone'])
        validate_password(attrs['password'], User(**{key: value for key, value in attrs.items() if key != 'password'}))
        return attrs

    def create(self, validated_data):
        return register(validated_data)


class Register(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegistrationSerializer
    throttle_scope = 'auth'


class SessionLoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['session_version'] = user.session_version
        return token


class Login(TokenObtainPairView):
    serializer_class = SessionLoginSerializer
    throttle_scope = 'auth'


class CheckedRefreshSerializer(TokenRefreshSerializer):
    @transaction.atomic
    def validate(self, attrs):
        token = RefreshToken(attrs['refresh'])
        user = User.objects.select_for_update().filter(pk=token['user_id'], is_active=True).first()
        if (user is None or token.get('session_version', 0) != user.session_version
                or not constant_time_compare(token.get('hash_password', ''), get_md5_hash_password(user.password))):
            raise InvalidToken('This session has been revoked.')
        return super().validate(attrs)


class Refresh(TokenRefreshView):
    serializer_class = CheckedRefreshSerializer
    throttle_scope = 'auth'


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class Logout(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(responses={204: None})
    @transaction.atomic
    def post(self, request):
        User.objects.select_for_update().get(pk=request.user.pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data['refresh'])
            if str(token['user_id']) != str(request.user.pk):
                raise InvalidToken()
            token.blacklist()
        except TokenError as error:
            raise InvalidToken(str(error)) from error
        return Response(status=status.HTTP_204_NO_CONTENT)


class Profile(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user


class PasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(trim_whitespace=False, max_length=128, write_only=True)
    password = serializers.CharField(trim_whitespace=False, max_length=128, write_only=True)

    def validate_password(self, value):
        validate_password(value, self.context['request'].user)
        return value


class Password(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordSerializer
    throttle_scope = 'auth'

    @extend_schema(responses={204: None})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_password(request.user, **serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)

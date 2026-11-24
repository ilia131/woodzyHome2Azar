from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


class SessionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if validated_token.get('session_version', 0) != user.session_version:
            raise InvalidToken('This session has been revoked.')
        return user


class SessionJWTScheme(SimpleJWTScheme):
    target_class = SessionJWTAuthentication
    priority = 1

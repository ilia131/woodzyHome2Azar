from typing import Protocol

from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import OutstandingToken, BlacklistedToken

from core.admin_api import audit
from .models import User


class PhoneOwnershipVerifier(Protocol):
    """Future adapter. Phase 0 does not issue or send challenges."""

    def verify(self, phone: str, challenge: str, proof: str) -> bool: ...


class RecoveryDelivery(Protocol):
    def deliver(self, user: User, token: str) -> None: ...


def register(data):
    try:
        with transaction.atomic():
            return User.objects.create_user(**data)
    except IntegrityError as error:
        if User.objects.filter(phone=data['phone']).exists():
            raise ValidationError({'phone': 'This phone is already registered.'}) from error
        raise


@transaction.atomic
def change_password(user, old_password, password):
    user = User.objects.select_for_update().get(pk=user.pk)
    if not user.check_password(old_password):
        raise ValidationError({'old_password': 'Incorrect password.'})
    validate_password(password, user)
    user.set_password(password)
    user.save(update_fields=['password'])
    blacklist_sessions(user)


def blacklist_sessions(user):
    tokens = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token_id=pk) for pk in tokens.values_list('pk', flat=True)], ignore_conflicts=True,
    )


@transaction.atomic
def update_profile(user, values):
    account = User.objects.select_for_update().get(pk=user.pk)
    if not account.is_active or account.session_version != user.session_version:
        raise AuthenticationFailed('The account session has been revoked.')
    if values:
        for field, value in values.items():
            setattr(account, field, value)
        account.save(update_fields=list(values))
    return account


def change_customer_activity(actor, account, active):
    # The admin view locks the account before invoking this service.
    if account.is_active != active:
        account.is_active = active
        account.session_version += 1
        account.save(update_fields=['is_active', 'session_version'])
        blacklist_sessions(account)
        audit(actor, 'activate' if active else 'deactivate', account)
    return account

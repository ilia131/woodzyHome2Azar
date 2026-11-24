import re
import unicodedata

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from core.images import validate_image


def normalize_phone(phone):
    phone = ''.join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in phone)
    phone = re.sub(r'[\s()-]', '', phone)
    if re.fullmatch(r'09[0-9]{9}', phone):
        phone = '+98' + phone[1:]
    if phone.startswith('00'):
        phone = '+' + phone[2:]
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', phone):
        raise ValidationError('Enter an international phone number or an Iranian mobile number.')
    if phone.startswith('+98') and not re.fullmatch(r'\+989[0-9]{9}', phone):
        raise ValidationError('Enter a valid Iranian mobile number.')
    return phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, username):
        try:
            phone = normalize_phone(username)
        except ValidationError:
            raise self.model.DoesNotExist from None
        return self.get(phone=phone)

    def create_user(self, phone, password=None, **extra):
        user = self.model(phone=normalize_phone(phone), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        for flag in ('is_active', 'is_staff', 'is_superuser'):
            if extra.setdefault(flag, True) is not True:
                raise ValueError(f'{flag} must be true for a superuser.')
        return self.create_user(phone, password, **extra)


class User(AbstractUser):
    username = None
    phone = models.CharField(max_length=16, unique=True)
    session_version = models.PositiveIntegerField(default=0, editable=False)
    phone_verified_at = models.DateTimeField(null=True, blank=True, editable=False)
    recovery_email = models.EmailField(blank=True, editable=False)
    recovery_revision = models.PositiveIntegerField(default=0, editable=False)
    avatar = models.ImageField(upload_to='avatars/', blank=True, validators=[validate_image])
    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []
    objects = UserManager()

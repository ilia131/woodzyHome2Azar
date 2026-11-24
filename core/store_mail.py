import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from kombu.exceptions import OperationalError
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class MailUnavailable(APIException):
    status_code = 503
    default_detail = 'Email delivery is unavailable.'


def require_mail():
    if not settings.TRANSACTIONAL_EMAIL_ENABLED:
        raise MailUnavailable()


def enqueue(task, *args):
    try:
        task.apply_async(args, argsrepr='(redacted)', kwargsrepr='{}', expires=300, retry=False)
    except OperationalError as error:
        raise MailUnavailable() from error


def deliver(subject, token, address):
    try:
        sent = send_mail(subject, f'WoodzyHome\n\nCode: {token}\n\nIf you did not request this, ignore this message.',
                         settings.DEFAULT_FROM_EMAIL, [address])
        if sent != 1:
            logger.warning('Transactional email was not accepted for delivery.')
    except (OSError, ValueError):
        logger.warning('Transactional email was not accepted for delivery.')


@shared_task(ignore_result=True)
def send_transactional_email(subject, token, address):
    deliver(subject, token, address)

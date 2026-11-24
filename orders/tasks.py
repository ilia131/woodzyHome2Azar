from celery import shared_task

from .inventory import expire_due


@shared_task(acks_late=True)
def expire_reservations():
    return expire_due()

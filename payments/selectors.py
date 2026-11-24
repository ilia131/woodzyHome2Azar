from .models import Payment


def owned_payments(user):
    return Payment.objects.filter(user=user).order_by('-created_at', '-pk')

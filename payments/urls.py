from django.urls import path

from .api import (
    AdminPaymentDetail, AdminPaymentList, AdminProviderAvailability, AdminReconciliation, AdminRefunds, AdminTransactions,
    InitiatePayment, MockPayment, PaymentCallback, PaymentDetail, PaymentList, SimulateRefund,
)


urlpatterns = [
    path('payments/initiate/', InitiatePayment.as_view(), name='payment-initiate'),
    path('payments/', PaymentList.as_view(), name='payment-list'),
    path('payments/<int:pk>/', PaymentDetail.as_view(), name='payment-detail'),
    path('payments/<int:pk>/status/', PaymentDetail.as_view(), name='payment-status'),
    path('payments/callback/<slug:provider>/', PaymentCallback.as_view(), name='payment-callback'),
    path('payments/mock/<int:pk>/simulate/', MockPayment.as_view(), name='mock-payment'),
    path('admin/payments/providers/', AdminProviderAvailability.as_view(), name='admin-payment-providers'),
    path('admin/payments/', AdminPaymentList.as_view(), name='admin-payments'),
    path('admin/payments/transactions/', AdminTransactions.as_view(), name='admin-payment-transactions'),
    path('admin/payments/reconciliation/', AdminReconciliation.as_view(), name='admin-payment-reconciliation'),
    path('admin/payments/<int:pk>/', AdminPaymentDetail.as_view(), name='admin-payment-detail'),
    path('admin/payments/<int:pk>/refunds/<int:refund_id>/simulate/', SimulateRefund.as_view(),
         name='admin-simulate-refund'),
    path('admin/payments/<int:pk>/refunds/', AdminRefunds.as_view(), name='admin-payment-refunds'),
]

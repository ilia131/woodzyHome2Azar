from django.conf import settings
from django.db.models import Q
from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from core.admin_api import StaffModelPermissions
from orders.api import PrivateCommerceAPI
from .models import Payment, PaymentTransaction, Refund
from .providers import provider_for
from .providers.registry import provider_availability
from .selectors import owned_payments
from .services import callback, initiate, request_refund, simulate_refund


class PaymentSerializer(serializers.ModelSerializer):
    payment_url = serializers.CharField(read_only=True, help_text="Provider URL or a same-origin Mock path.")

    class Meta:
        model = Payment
        fields = ('id', 'order', 'provider', 'amount', 'currency', 'status', 'provider_reference',
                  'payment_url', 'expires_at', 'completed_at', 'created_at')
        read_only_fields = fields


class AdminPaymentSerializer(PaymentSerializer):
    class Meta(PaymentSerializer.Meta):
        fields = (*PaymentSerializer.Meta.fields, 'user', 'review_reason')
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ('id', 'payment', 'provider', 'provider_transaction_id', 'transaction_type', 'status', 'amount',
                  'error_code', 'sanitized_metadata', 'created_at')
        read_only_fields = fields


class InitiationSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    provider = serializers.SlugField(max_length=50, default=lambda: settings.PAYMENT_DEFAULT_PROVIDER)
    idempotency_key = serializers.UUIDField()


class CallbackSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    reference = serializers.CharField(max_length=128)
    timestamp = serializers.IntegerField()


class ScenarioSerializer(serializers.Serializer):
    scenario = serializers.ChoiceField(choices=('success', 'failure', 'cancel', 'timeout', 'invalid_signature',
                                               'invalid_amount', 'invalid_reference', 'invalid_verification', 'delayed'))


class PaymentList(PrivateCommerceAPI, generics.ListAPIView):
    serializer_class = PaymentSerializer
    queryset = Payment.objects.none()
    throttle_scope = 'payments'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_payments(self.request.user)


class PaymentDetail(PrivateCommerceAPI, generics.RetrieveAPIView):
    serializer_class = PaymentSerializer
    queryset = Payment.objects.none()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return self.queryset
        return owned_payments(self.request.user)


class ProviderUnavailableSerializer(serializers.Serializer):
    code = serializers.CharField()
    provider = serializers.CharField()
    detail = serializers.CharField()


class ProviderAvailabilitySerializer(serializers.Serializer):
    provider = serializers.CharField()
    display_name = serializers.CharField()
    registered = serializers.BooleanField()
    configured = serializers.BooleanField()
    enabled = serializers.BooleanField()
    enable_requested = serializers.BooleanField()
    ready = serializers.BooleanField(help_text='Ready for real transactions.')
    status = serializers.CharField()
    pending_documentation = serializers.ListField(child=serializers.CharField())
    missing_configuration = serializers.ListField(child=serializers.CharField())


class AdminProviderAvailability(generics.GenericAPIView):
    queryset = Payment.objects.none()
    permission_classes = [StaffModelPermissions]
    serializer_class = ProviderAvailabilitySerializer

    @extend_schema(responses=ProviderAvailabilitySerializer(many=True))
    def get(self, request):
        return Response(self.get_serializer(list(provider_availability()), many=True).data)


class InitiatePayment(PrivateCommerceAPI, generics.GenericAPIView):
    serializer_class = InitiationSerializer
    throttle_scope = 'payments'

    @extend_schema(responses={200: PaymentSerializer, 201: PaymentSerializer, 503: ProviderUnavailableSerializer})
    def post(self, request):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment, created = initiate(request.user, **data.validated_data)
        return Response(PaymentSerializer(payment).data, status=201 if created else 200)


class PaymentCallback(generics.GenericAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = CallbackSerializer
    throttle_scope = 'payment_callback'

    @extend_schema(parameters=[OpenApiParameter('X-Payment-Signature', str, OpenApiParameter.HEADER,
                                               description='Required by Mock only.')],
                   description='The request payload and signature shown apply only to Mock. '
                               'Pending providers reject the request before reading the callback payload.',
                   responses={200: PaymentSerializer, 403: None, 404: None, 503: ProviderUnavailableSerializer})
    def post(self, request, provider):
        provider_for(provider)
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = callback(provider, data.validated_data, request.headers.get('X-Payment-Signature', ''))
        return Response(PaymentSerializer(payment).data)


class MockPayment(PaymentDetail):
    throttle_scope = 'payments'

    def get_object(self):
        provider_for('mock')
        return super().get_object()

    @extend_schema(request=ScenarioSerializer, responses={200: PaymentSerializer})
    def post(self, request, pk):
        adapter = provider_for('mock')
        payment = self.get_object()
        if payment.provider != 'mock' or not payment.provider_reference:
            from rest_framework.exceptions import NotFound
            raise NotFound('Mock session unavailable.')
        data = ScenarioSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payload, signature = adapter.simulate(payment.provider_reference, data.validated_data['scenario'])
        return Response(PaymentSerializer(callback('mock', payload, signature)).data)


class PaymentFilter(django_filters.FilterSet):
    created_from = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_to = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Payment
        fields = ('status', 'provider')


class AdminPaymentList(generics.ListAPIView):
    queryset = Payment.objects.order_by('-created_at', '-pk')
    serializer_class = AdminPaymentSerializer
    permission_classes = [StaffModelPermissions]
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter]
    filterset_class = PaymentFilter
    search_fields = ('order__order_number', 'provider_reference')


class AdminPaymentDetail(generics.RetrieveAPIView):
    queryset = Payment.objects.all()
    serializer_class = AdminPaymentSerializer
    permission_classes = [StaffModelPermissions]


class AdminTransactions(generics.ListAPIView):
    queryset = PaymentTransaction.objects.order_by('-created_at', '-pk')
    serializer_class = TransactionSerializer
    permission_classes = [StaffModelPermissions]
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = ('payment', 'status', 'provider', 'transaction_type')


class AdminReconciliation(AdminPaymentList):
    def get_queryset(self):
        from django.utils import timezone
        return super().get_queryset().filter(
            Q(status__in=['processing', 'requires_review', 'expired'])
            | Q(status__in=['created', 'pending'], expires_at__lte=timezone.now())
            | (Q(status__in=['succeeded', 'partially_refunded', 'refunded']) &
               ~Q(order__status__in=['paid', 'processing', 'completed']))
        )


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ('id', 'payment', 'amount', 'status', 'provider_reference', 'created_at')
        read_only_fields = fields


class RefundRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=32, decimal_places=2)
    idempotency_key = serializers.UUIDField()


class AdminRefunds(generics.GenericAPIView):
    queryset = Refund.objects.all()
    serializer_class = RefundSerializer
    permission_classes = [StaffModelPermissions]

    @extend_schema(request=RefundRequestSerializer, responses={200: RefundSerializer})
    def post(self, request, pk):
        data = RefundRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        refund = request_refund(pk, request.user, data.validated_data['amount'], data.validated_data['idempotency_key'])
        return Response(RefundSerializer(refund).data)


class SimulateRefund(generics.GenericAPIView):
    queryset = Refund.objects.all()
    serializer_class = RefundSerializer
    permission_classes = [StaffModelPermissions]

    @extend_schema(request=None, responses={200: RefundSerializer})
    def patch(self, request, pk, refund_id):
        refund = simulate_refund(pk, refund_id, request.user)
        return Response(self.get_serializer(refund).data)

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, viewsets
from rest_framework.response import Response

from core.admin_api import StaffModelPermissions
from .inventory import InventoryConflict, adjust_available
from .lifecycle import staff_transition
from .models import InventoryMovement, Order, Reservation
from .serializers import CommerceErrorSerializer, OrderSerializer


class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = ('id', 'order_id', 'item_id', 'product_id', 'quantity', 'status', 'reserved_at', 'expires_at',
                  'released_at', 'consumed_at')


class AdminOrderSerializer(OrderSerializer):
    user_id = serializers.IntegerField(read_only=True)
    reservations = ReservationSerializer(many=True, read_only=True)

    class Meta(OrderSerializer.Meta):
        fields = (*OrderSerializer.Meta.fields, 'user_id', 'reservations')


class OrderFilter(filters.FilterSet):
    created_from = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_to = filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Order
        fields = ('order_number', 'user', 'status')


class AdminOrders(viewsets.ReadOnlyModelViewSet):
    queryset = Order.objects.prefetch_related('items', 'reservations').order_by('-created_at', '-pk')
    serializer_class = AdminOrderSerializer
    permission_classes = [StaffModelPermissions]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_class = OrderFilter


class OrderTransitionSerializer(serializers.Serializer):
    expected_status = serializers.ChoiceField(choices=Order.Status.choices)
    status = serializers.ChoiceField(choices=('cancelled', 'processing', 'completed'))


class AdminOrderTransition(generics.GenericAPIView):
    queryset = Order.objects.none()
    serializer_class = OrderTransitionSerializer
    permission_classes = [StaffModelPermissions]

    @extend_schema(responses={200: AdminOrderSerializer, 409: CommerceErrorSerializer})
    def patch(self, request, pk):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        order = staff_transition(request.user, pk, **data.validated_data)
        if order is None:
            raise InventoryConflict('The reservation expired.')
        return Response(AdminOrderSerializer(order).data)


class MovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryMovement
        fields = ('id', 'product_id_snapshot', 'order_id', 'item_id', 'kind', 'quantity', 'available_delta',
                  'available_after', 'actor', 'metadata', 'created_at')


class AdminMovements(generics.ListAPIView):
    queryset = InventoryMovement.objects.order_by('-created_at', '-pk')
    serializer_class = MovementSerializer
    permission_classes = [StaffModelPermissions]
    filter_backends = [filters.DjangoFilterBackend]
    filterset_fields = ('product_id_snapshot', 'order', 'kind')


class AdjustmentSerializer(serializers.Serializer):
    delta = serializers.IntegerField(min_value=-2147483647, max_value=2147483647, required=False)
    target = serializers.IntegerField(min_value=0, max_value=2147483647, required=False)
    expected_revision = serializers.IntegerField(min_value=1, required=False)
    operation_id = serializers.UUIDField()

    def validate(self, attrs):
        if ('target' in attrs) == ('delta' in attrs):
            raise serializers.ValidationError('Provide exactly one of target or delta.')
        if ('target' in attrs) != ('expected_revision' in attrs):
            raise serializers.ValidationError('expected_revision is required only for an absolute target.')
        return attrs

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError('Enter a nonzero adjustment.')
        return value


class AdminStockAdjustment(generics.GenericAPIView):
    queryset = InventoryMovement.objects.none()
    serializer_class = AdjustmentSerializer
    permission_classes = [StaffModelPermissions]

    @extend_schema(responses={200: MovementSerializer, 409: CommerceErrorSerializer})
    def post(self, request, pk):
        data = self.get_serializer(data=request.data)
        data.is_valid(raise_exception=True)
        event = adjust_available(pk, request.user, **data.validated_data)
        return Response(MovementSerializer(event).data)

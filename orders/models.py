from django.conf import settings
from django.db import models


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=60, blank=True)
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=16)
    province = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    address_line = models.CharField(max_length=500)
    postal_code = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user'], condition=models.Q(is_default=True),
                                    name='one_default_address_per_user'),
        ]


class CartItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='one_cart_item_per_user_product'),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name='cart_item_quantity_positive'),
        ]


    @property
    def product_title(self):
        return self.product.title if self.product_visible else None

    @property
    def unit_price(self):
        return self.product.effective_price if self.product_visible else None

    @property
    def line_total(self):
        price = self.unit_price
        return None if price is None else price * self.quantity

    @property
    def availability(self):
        if not self.product_visible:
            return 'not_visible'
        if self.product.stock == 0:
            return 'out_of_stock'
        return 'insufficient_stock' if self.quantity > self.product.stock else 'available'


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = 'pending_payment', 'Pending payment'
        CANCELLED = 'cancelled', 'Cancelled'
        EXPIRED = 'expired', 'Expired'
        PAYMENT_REVIEW = 'payment_review', 'Payment review'
        PAID = 'paid', 'Paid'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'

    order_number = models.CharField(max_length=32, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    shipping_address = models.ForeignKey(Address, null=True, on_delete=models.SET_NULL, related_name='orders')
    shipping_address_snapshot = models.JSONField()
    status = models.CharField(max_length=24, choices=Status, default=Status.PENDING_PAYMENT)
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=32, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=32, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=32, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=32, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at', '-id'], name='orders_user_latest_idx')]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0, discount_amount__gte=0, shipping_amount__gte=0,
                                   total_amount__gte=0, discount_amount__lte=models.F('subtotal'),
                                   total_amount=models.F('subtotal') - models.F('discount_amount') +
                                   models.F('shipping_amount')),
                name='order_valid_amounts',
            ),
        ]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', null=True, on_delete=models.SET_NULL, related_name='order_items')
    product_title = models.CharField(max_length=200)
    product_slug = models.CharField(max_length=220)
    product_sku = models.CharField(max_length=64)
    product_main_image = models.CharField(max_length=255, blank=True)
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=26, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, unit_price__gte=0,
                                   line_total=models.F('unit_price') * models.F('quantity')),
                name='order_item_valid_amounts',
            ),
        ]


class Reservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active'
        RELEASED = 'released'
        EXPIRED = 'expired'
        CONSUMED = 'consumed'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='reservations')
    item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name='reservations')
    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=12, choices=Status, default=Status.ACTIVE)
    reserved_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True)
    consumed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'expires_at', 'order'], name='reservations_due_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0, expires_at__gt=models.F('reserved_at')),
                                   name='reservation_positive_and_timed'),
            models.UniqueConstraint(fields=['item'], condition=models.Q(status='active'),
                                    name='reservation_one_active_per_item'),
            models.CheckConstraint(condition=(
                models.Q(status='active', product__isnull=False, released_at__isnull=True, consumed_at__isnull=True)
                | models.Q(status__in=['released', 'expired'], released_at__isnull=False, consumed_at__isnull=True)
                | models.Q(status='consumed', consumed_at__isnull=False, released_at__isnull=True)
            ), name='reservation_consistent_state'),
        ]


class InventoryMovement(models.Model):
    class Kind(models.TextChoices):
        INITIAL = 'initial'
        RESERVE = 'reserve'
        RELEASE = 'release'
        EXPIRE = 'expire'
        CONSUME = 'consume'
        ADJUST = 'adjust'

    product = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True)
    product_id_snapshot = models.PositiveBigIntegerField()
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True)
    item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True)
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, null=True)
    kind = models.CharField(max_length=12, choices=Kind)
    quantity = models.PositiveIntegerField()
    available_delta = models.IntegerField()
    available_after = models.PositiveIntegerField()
    operation_key = models.CharField(max_length=120, unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['product_id_snapshot', '-created_at'], name='inventory_product_time_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='inventory_positive_quantity'),
            models.UniqueConstraint(fields=['reservation'], condition=models.Q(kind__in=['release', 'expire', 'consume']),
                                    name='one_terminal_inventory_movement'),
            models.UniqueConstraint(fields=['reservation'], condition=models.Q(kind='reserve'),
                                    name='one_reserve_inventory_movement'),
        ]

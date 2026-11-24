from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.db.models import F, Q
from django.core.validators import MinValueValidator

from core.images import product_image_path, gallery_image_path, validate_image
from core.text import normalize


class Product(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, allow_unicode=True)
    short_description = models.CharField(max_length=500)
    description = models.TextField()
    main_image = models.ImageField(upload_to=product_image_path, blank=True, validators=[validate_image])
    price = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    discount_price = models.DecimalField(max_digits=16, decimal_places=2, blank=True, null=True,
                                         validators=[MinValueValidator(Decimal('0'))])
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=64, unique=True)
    category = models.ForeignKey('categories.Category', on_delete=models.PROTECT, related_name='products')
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    search_title = models.TextField(editable=False)
    search_text = models.TextField(editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(price__gt=0), name='product_positive_price'),
            models.CheckConstraint(condition=Q(discount_price__isnull=True) |
                Q(discount_price__gte=0, discount_price__lt=F('price')), name='product_valid_discount'),
        ]

    def clean(self):
        if self.discount_price is not None and self.price is not None and self.discount_price >= self.price:
            raise ValidationError({'discount_price': 'Discount price must be below list price.'})

    def save(self, *args, **kwargs):
        database = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=database):
            rows = type(self).objects.using(database)
            previous = rows.select_for_update().filter(pk=self.pk).first() if self.pk else None
            fields = kwargs.get('update_fields')
            if fields is not None:
                fields = set(fields)
                if not fields:
                    return
            if previous and (fields is None or 'slug' in fields) and previous.slug != self.slug:
                raise ValidationError({'slug': 'A published product URL cannot be changed.'})
            if fields is None or fields.intersection({'title', 'short_description', 'description'}):
                def value(name):
                    return getattr(self if fields is None or name in fields else previous, name)

                self.search_title = normalize(value('title'))
                self.search_text = normalize(' '.join(value(name) for name in ('title', 'short_description', 'description')))
                if fields is not None:
                    kwargs['update_fields'] = fields | {'search_title', 'search_text'}
            super().save(*args, **kwargs)
            tracked = ('price', 'discount_price', 'stock')
            snapshot = {name: getattr(self if not previous or fields is None or name in fields else previous, name)
                        for name in tracked}
            if previous is None or any(snapshot[name] != getattr(previous, name) for name in tracked):
                ProductChange.objects.using(database).create(product=self, **snapshot)

    @property
    def effective_price(self):
        return self.price if self.discount_price is None else self.discount_price

    @property
    def discount_percentage(self):
        return ((self.price - self.effective_price) * 100 / self.price).quantize(Decimal('0.01'))

    @property
    def in_stock(self):
        return self.stock > 0

    def __str__(self):
        return self.title


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='gallery')
    image = models.ImageField(upload_to=gallery_image_path, validators=[validate_image])
    alt_text = models.CharField(max_length=220, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'pk']


class ProductChange(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='changes')
    price = models.DecimalField(max_digits=16, decimal_places=2)
    discount_price = models.DecimalField(max_digits=16, decimal_places=2, null=True)
    stock = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

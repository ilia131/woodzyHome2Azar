from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import User
from categories.models import Category
from products.models import Product


@override_settings(SITE_URL='https://store.example')
class CatalogTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.root = Category.objects.create(name='مبلمان', slug='مبلمان')
        self.category = Category.objects.create(name='میز', slug='میز', parent=self.root)
        self.product = Product.objects.create(
            title='میز چوبی', slug='میز-چوبی', sku='TABLE-1', category=self.category,
            short_description='میز کوچک', description='میز از چوب طبیعی', price='100.00',
            discount_price='80.00', stock=4,
        )
        self.path = f'/api/v1/products/{self.product.slug}/'

    def user(self, number=1, **settings):
        return User.objects.create_user(f'0912123456{number}', **settings)

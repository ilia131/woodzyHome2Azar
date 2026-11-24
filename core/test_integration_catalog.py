from rest_framework.test import APITestCase

from accounts.models import User
from categories.models import Category
from favorites.models import Favorite
from orders.models import Order, OrderItem
from products.models import Product


class IntegrationCatalogTests(APITestCase):
    def setUp(self):
        category = Category.objects.create(name='Living', slug='living')
        self.product = Product.objects.create(title='Sofa', slug='sofa', sku='SOFA', category=category, price=50)
        self.other_product = Product.objects.create(title='Chair', slug='chair', sku='CHAIR', category=category, price=50)
        self.user = User.objects.create_user('09120000000')
        self.other = User.objects.create_user('09120000001')

    def test_batch_favorites_is_private_and_scoped_to_the_caller(self):
        Favorite.objects.create(user=self.user, product=self.product)
        Favorite.objects.create(user=self.other, product=self.other_product)
        url = f'/api/v1/favorites/status/?ids={self.product.pk},{self.other_product.pk}'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(self.user)
        response = self.client.get(url)
        self.assertEqual(response.data, {'ids': [self.product.pk]})
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(self.client.get('/api/v1/favorites/status/?ids=0').status_code, 400)

    def test_best_selling_excludes_incomplete_orders(self):
        for index, (product, status, quantity) in enumerate([
            (self.product, Order.Status.COMPLETED, 2),
            (self.other_product, Order.Status.PENDING_PAYMENT, 5),
        ]):
            amount = 50 * quantity
            order = Order.objects.create(user=self.user, order_number=f'TEST-{index}', status=status,
                                         shipping_address_snapshot={}, subtotal=amount, total_amount=amount, currency='IRR')
            OrderItem.objects.create(order=order, product=product, product_title=product.title,
                                     product_slug=product.slug, product_sku=product.sku, unit_price=50,
                                     quantity=quantity, line_total=amount)
        response = self.client.get('/api/v1/products/best-selling/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p['id'] for p in response.data['results']], [self.product.pk])

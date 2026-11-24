import tempfile
from io import BytesIO

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from PIL import Image

from core.models import AuditLog
from core.test_catalog import CatalogTestCase
from .models import Product, ProductChange, ProductImage


class ProductTests(CatalogTestCase):
    def test_multi_product_price_filters_and_pagination(self):
        Product.objects.create(title='صندلی', slug='صندلی', sku='CHAIR-2', category=self.root,
                               short_description='صندلی', description='چوب', price='70', stock=0)
        response = self.client.get('/api/v1/products/', {'category': self.root.slug, 'ordering': 'price', 'page_size': 1})
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['slug'], 'صندلی')
        response = self.client.get('/api/v1/products/', {'in_stock': 'true', 'min_price': 75, 'max_price': 85})
        self.assertEqual(response.data['count'], 1)
        detail = self.client.get(self.path)
        self.assertEqual(detail.data['discount_percentage'], '20.00')
        self.assertEqual(detail.data['effective_price'], '80.00')

    def test_history_validation_and_audit(self):
        staff = self.user(is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(content_type__app_label='products',
                                   codename__in=('change_product', 'view_product', 'view_productchange')))
        self.client.force_authenticate(staff)
        url = f'/api/v1/admin/products/{self.product.pk}/'
        self.assertEqual(self.client.patch(url, {'price': '75.00'}).status_code, 400)
        self.assertEqual(self.client.patch(url, {'slug': 'different'}).status_code, 400)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label='orders',
                                                          codename='add_inventorymovement'))
        self.client.force_authenticate(type(staff).objects.get(pk=staff.pk))
        revision = self.client.get(url).data['stock_revision']
        self.assertEqual(self.client.patch(url, {'stock': 1, 'stock_revision': revision, 'price': '120.00'}).status_code, 200)
        self.assertEqual(self.client.patch(url, {'title': 'New title'}).status_code, 200)
        self.assertEqual(list(ProductChange.objects.order_by('pk').values_list('stock', flat=True)), [4, 1])
        self.assertEqual(AuditLog.objects.filter(actor=staff, action='update').count(), 2)
        history = self.client.get('/api/v1/admin/product-history/', {'product': self.product.pk})
        self.assertEqual(history.data['count'], 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.filter(pk=self.product.pk).update(discount_price=200)

    def test_public_and_staff_permissions(self):
        url = '/api/v1/admin/products/'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_authenticate(self.user(is_staff=True))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.force_authenticate(self.user(2))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.patch(self.path, {'stock': 50}).status_code, 405)

    def test_unique_unicode_slug_and_admin_create(self):
        admin = self.user(is_staff=True, is_superuser=True)
        self.client.force_authenticate(admin)
        url = '/api/v1/admin/products/'
        data = {'title': 'کنسول', 'slug': 'کنسول-چوبی', 'sku': 'CONSOLE-2', 'price': '30.00',
                'category': self.category.pk, 'short_description': 'کنسول', 'description': 'کنسول چوبی'}
        result = self.client.post(url, data)
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(self.client.post(url, {**data, 'sku': 'CONSOLE-3'}).status_code, 400)
        self.assertEqual(self.client.post(url, {**data, 'slug': 'bad slug', 'sku': 'CONSOLE-3'}).status_code, 400)
        self.assertEqual(self.client.post(url, {**data, 'slug': 'most-viewed', 'sku': 'CONSOLE-3'}).status_code, 400)


class ImageTests(CatalogTestCase):
    def png(self, name, padding=0):
        stream = BytesIO()
        Image.new('RGB', (16, 16)).save(stream, 'PNG')
        return SimpleUploadedFile(name, stream.getvalue() + bytes(padding), content_type='image/png')

    def test_gallery_upload_order_scope_and_validation(self):
        admin = self.user(is_staff=True, is_superuser=True)
        self.client.force_authenticate(admin)
        url = '/api/v1/admin/product-images/'
        uploads = [
            (20, self.png('back.png')), (10, self.png('front.png')),
            (30, SimpleUploadedFile('invalid.png', b'not an image', content_type='image/png')),
            (30, self.png('large.png', 5 * 1024 * 1024)),
            (30, self.png('mismatch.svg')),
            (30, self.png('mismatch.jpg')),
        ]
        with tempfile.TemporaryDirectory() as directory, self.settings(MEDIA_ROOT=directory):
            for index, (position, upload) in enumerate(uploads):
                response = self.client.post(url, {'product': self.product.pk, 'position': position, 'image': upload},
                                            format='multipart')
                self.assertEqual(response.status_code, 201 if index < 2 else 400, response.data)
            result = self.client.get(self.path).data
            self.assertEqual([item['position'] for item in result['gallery']], [10, 20])
            self.assertTrue(all('/media/gallery/' in item['image'] for item in result['gallery']))
            self.assertEqual(len(result['seo']['structured_data']['image']), 2)
        self.assertEqual(ProductImage.objects.count(), 2)


class PublicCatalogVisibilityTests(CatalogTestCase):
    def test_every_product_surface_hides_inactive_products_and_category_descendants(self):
        from urllib.parse import quote
        from categories.models import Category
        from favorites.models import Favorite

        inactive_parent = Category.objects.create(name='Hidden parent', slug='hidden-parent', is_active=False)
        hidden_child = Category.objects.create(name='Hidden child', slug='hidden-child', parent=inactive_parent)
        hidden_leaf = Category.objects.create(name='Hidden leaf', slug='hidden-leaf', parent=hidden_child)
        inactive = Product.objects.create(title='Inactive product', slug='inactive-product', sku='HIDDEN-1',
                                          category=self.category, price=100, discount_price=70, is_active=False)
        descendant = Product.objects.create(title='Hidden descendant', slug='hidden-descendant', sku='HIDDEN-2',
                                            category=hidden_leaf, price=100, discount_price=70)
        user = self.user()
        for product in (self.product, inactive, descendant):
            Favorite.objects.create(user=user, product=product)
        self.client.force_authenticate(user)
        for url in ('/api/v1/products/', '/api/v1/products/most-viewed/', '/api/v1/products/most-favorited/',
                    '/api/v1/products/best-discounts/', '/api/v1/favorites/'):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row['id'] for row in response.data['results']], [self.product.pk])
        for hidden in (inactive, descendant):
            with self.subTest(product=hidden.slug):
                self.assertEqual(self.client.get(f'/api/v1/products/{hidden.slug}/').status_code, 404)
                self.assertEqual(self.client.post(f'/api/v1/favorites/{hidden.pk}/').status_code, 404)
                self.assertFalse(hidden.views.exists())
                self.assertNotContains(self.client.get('/sitemap.xml'), quote(hidden.slug))
        for category in (inactive_parent, hidden_child, hidden_leaf):
            self.assertEqual(self.client.get(f'/api/v1/categories/{category.slug}/').status_code, 404)
            self.assertEqual(self.client.get(f'/api/v1/categories/{category.slug}/children/').status_code, 404)
            self.assertEqual(self.client.get('/api/v1/products/', {'category': category.slug}).data['count'], 0)
        self.assertEqual(self.client.get('/api/v1/categories/').data['count'], 2)

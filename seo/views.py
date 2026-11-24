from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.http import HttpResponse
from django.db.models import Q
from django.views.decorators.http import require_safe

from categories.selectors import visible_category_ids
from products.models import Product
from .services import product_url


@require_safe
def sitemap(request):
    root = Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    products = Product.objects.filter(is_active=True, category_id__in=visible_category_ids()).filter(
        Q(seo__isnull=True) | Q(seo__robots_index=True)).select_related('seo').order_by('pk')
    for product in products.iterator():
        url = product_url(product)
        if hasattr(product, 'seo') and product.seo.canonical_url and product.seo.canonical_url != url:
            continue
        item = SubElement(root, 'url')
        SubElement(item, 'loc').text = url
        SubElement(item, 'lastmod').text = product.updated_at.isoformat()
    return HttpResponse(tostring(root, encoding='utf-8', xml_declaration=True), content_type='application/xml')


@require_safe
def robots(request):
    return HttpResponse(f'User-agent: *\nDisallow: /api/v1/admin/\nDisallow: /django-admin/\n'
                        f'Sitemap: {settings.SITE_URL}/sitemap.xml\n', content_type='text/plain')

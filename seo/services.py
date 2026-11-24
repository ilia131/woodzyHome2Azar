from urllib.parse import quote
from django.conf import settings


def product_url(product):
    return f'{settings.SITE_URL}/products/{quote(product.slug)}/'


def metadata(product, request):
    entry = getattr(product, 'seo', None)
    title = (entry and entry.meta_title) or product.title
    description = (entry and entry.meta_description) or product.short_description
    canonical = (entry and entry.canonical_url) or product_url(product)

    def image_url(field):
        return request.build_absolute_uri(field.url) if field else None

    image = image_url(product.main_image)
    gallery = [image_url(item.image) for item in product.gallery.all()]
    images = list(dict.fromkeys(url for url in [image, *gallery] if url))
    og_image = image_url(entry.og_image) if entry and entry.og_image else next(iter(images), None)
    og_title = (entry and entry.og_title) or title
    og_description = (entry and entry.og_description) or description
    structured = dict(entry.structured_data) if entry else {}
    structured.update({
        '@context': 'https://schema.org', '@type': 'Product', 'name': product.title,
        'description': product.short_description, 'sku': product.sku, 'image': images,
        'offers': {'@type': 'Offer', 'url': canonical, 'price': str(product.effective_price),
                   'priceCurrency': settings.CURRENCY,
                   'availability': 'https://schema.org/InStock' if product.in_stock else 'https://schema.org/OutOfStock'},
    })
    return {
        'meta_title': title, 'meta_description': description, 'meta_keywords': entry.meta_keywords if entry else '',
        'canonical_url': canonical, 'og_title': og_title, 'og_description': og_description, 'og_image': og_image,
        'open_graph': {'type': 'product', 'title': og_title, 'description': og_description, 'image': og_image,
                       'url': canonical},
        'twitter': {'card': 'summary_large_image' if og_image else 'summary', 'title': og_title,
                    'description': og_description, 'image': og_image},
        'structured_data': structured, 'robots_index': entry.robots_index if entry else True,
        'robots_follow': entry.robots_follow if entry else True,
    }

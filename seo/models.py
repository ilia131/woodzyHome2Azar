from django.db import models
from core.images import seo_image_path, validate_image


class ProductSEO(models.Model):
    product = models.OneToOneField('products.Product', related_name='seo', on_delete=models.CASCADE)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=500, blank=True)
    meta_keywords = models.CharField(max_length=400, blank=True)
    canonical_url = models.URLField(blank=True)
    og_title = models.CharField(max_length=200, blank=True)
    og_description = models.CharField(max_length=500, blank=True)
    og_image = models.ImageField(upload_to=seo_image_path, blank=True, validators=[validate_image])
    structured_data = models.JSONField(default=dict, blank=True)
    robots_index = models.BooleanField(default=True)
    robots_follow = models.BooleanField(default=True)

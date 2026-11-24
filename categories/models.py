from django.core.exceptions import ValidationError
from django.db import connections, models, router, transaction
from core.images import category_image_path, validate_image
from core.text import normalize
from .services import lock_hierarchy


class Category(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, allow_unicode=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to=category_image_path, blank=True, validators=[validate_image])
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    search_name = models.TextField(editable=False)

    def clean(self):
        visited = {self.pk}
        ancestor = self.parent
        while ancestor is not None:
            if ancestor.pk in visited:
                raise ValidationError({'parent': 'Category hierarchy cannot contain cycles.'})
            visited.add(ancestor.pk)
            ancestor = ancestor.parent

    def save(self, *args, **kwargs):
        database = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        fields = kwargs.get('update_fields')
        with transaction.atomic(using=database):
            if fields is None or {'parent', 'parent_id'}.intersection(fields):
                lock_hierarchy(connections[database])
                # Read parents again after taking the hierarchy lock.
                visited = {self.pk}
                parent_id = self.parent_id
                while parent_id is not None:
                    if parent_id in visited:
                        raise ValidationError({'parent': 'Category hierarchy cannot contain cycles.'})
                    visited.add(parent_id)
                    parent_id = type(self).objects.using(database).values_list('parent_id', flat=True).get(pk=parent_id)
            if fields is None or 'name' in fields:
                self.search_name = normalize(self.name)
                if fields is not None:
                    kwargs['update_fields'] = set(fields) | {'search_name'}
            super().save(*args, **kwargs)

    def __str__(self):
        return self.name

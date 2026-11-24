from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


# Owned by the search app and installed only on PostgreSQL.
INDEXES = (
    ('search_product_title_trgm', 'products_product', 'search_title gin_trgm_ops'),
    ('search_product_text_trgm', 'products_product', 'search_text gin_trgm_ops'),
    ('search_category_name_trgm', 'categories_category', 'search_name gin_trgm_ops'),
    ('search_product_text_fts', 'products_product', "(to_tsvector('simple'::regconfig, COALESCE(search_text, '')))"),
    ('search_category_name_fts', 'categories_category', "(to_tsvector('simple'::regconfig, COALESCE(search_name, '')))"),
)


def add_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        for name, table, expression in INDEXES:
            schema_editor.execute(f'CREATE INDEX {name} ON {table} USING GIN ({expression})')


def remove_indexes(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        for name, _, _ in reversed(INDEXES):
            schema_editor.execute(f'DROP INDEX {name}')


class Migration(migrations.Migration):
    dependencies = [
        ('search', '0001_initial'),
        ('products', '0002_alter_product_main_image_alter_productimage_image'),
        ('categories', '0002_alter_category_image'),
    ]
    operations = [TrigramExtension(), migrations.RunPython(add_indexes, remove_indexes)]

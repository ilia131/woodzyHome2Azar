from django.db import migrations


def seed_inventory(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    Movement = apps.get_model('orders', 'InventoryMovement')
    alias = schema_editor.connection.alias
    batch = []
    for pk, stock in Product.objects.using(alias).filter(stock__gt=0).values_list('id', 'stock').iterator():
        batch.append(Movement(product_id=pk, product_id_snapshot=pk, kind='initial', quantity=stock,
                              available_delta=stock, available_after=stock, operation_key=f'initial:{pk}'))
        if len(batch) == 1000:
            Movement.objects.using(alias).bulk_create(batch, ignore_conflicts=True)
            batch.clear()
    if batch:
        Movement.objects.using(alias).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [('orders', '0003_alter_order_status_reservation_inventorymovement_and_more')]
    operations = [migrations.RunPython(seed_inventory, migrations.RunPython.noop)]

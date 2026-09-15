from django.db import migrations


def forwards(apps, schema_editor):
    FeeStructure = apps.get_model('portal', 'FeeStructure')
    FeeStructureItem = apps.get_model('portal', 'FeeStructureItem')
    for structure in FeeStructure.objects.all():
        if structure.amount_required and structure.amount_required > 0:
            FeeStructureItem.objects.create(
                fee_structure=structure,
                description='Tuition Fee',
                amount=structure.amount_required,
                is_compulsory=True,
            )


def backwards(apps, schema_editor):
    FeeStructure = apps.get_model('portal', 'FeeStructure')
    FeeStructureItem = apps.get_model('portal', 'FeeStructureItem')
    for structure in FeeStructure.objects.all():
        first_item = structure.items.order_by('id').first()
        if first_item:
            structure.amount_required = first_item.amount
            structure.save(update_fields=['amount_required'])
    FeeStructureItem.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0075_add_fee_structure_item'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]

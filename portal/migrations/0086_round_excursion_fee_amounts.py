from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def round_excursion_amounts(apps, schema_editor):
    FeeStructureItem = apps.get_model('portal', 'FeeStructureItem')
    database = schema_editor.connection.alias
    items = FeeStructureItem.objects.using(database).filter(description__icontains='excursion')
    for item in items.iterator():
        amount = item.amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        if amount != item.amount:
            FeeStructureItem.objects.using(database).filter(pk=item.pk).update(amount=amount)


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0085_feestructureitem_payment_account'),
    ]

    operations = [
        migrations.RunPython(round_excursion_amounts, migrations.RunPython.noop),
    ]
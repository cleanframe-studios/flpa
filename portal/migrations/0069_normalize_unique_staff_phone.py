from django.db import migrations, models


def normalize_phone(value):
    return ''.join(character for character in str(value or '') if character.isdigit() or character == '+')


def normalize_existing_phones(apps, schema_editor):
    Parent = apps.get_model('portal', 'Parent')
    Teacher = apps.get_model('portal', 'Teacher')

    for Model in (Parent, Teacher):
        seen = set()
        for record in Model.objects.exclude(phone_number__isnull=True).iterator():
            normalized = normalize_phone(record.phone_number)
            if normalized in seen:
                raise RuntimeError(f'Duplicate normalized phone number found in {Model.__name__}: {normalized}')
            seen.add(normalized)
            if normalized != record.phone_number:
                Model.objects.filter(pk=record.pk).update(phone_number=normalized)


def reverse_normalize_existing_phones(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0068_notification'),
    ]

    operations = [
        migrations.RunPython(normalize_existing_phones, reverse_normalize_existing_phones),
        migrations.AlterField(
            model_name='teacher',
            name='phone_number',
            field=models.CharField(max_length=100, unique=True),
        ),
    ]

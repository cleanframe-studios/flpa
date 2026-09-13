from django.db import migrations

BOOK_DATA = {
    'KG 1': [
        ('Maths', 3500),
        ('English', 3500),
        ('Colouring / H.W', 4000),
        ('Exercise Books (10)', 5000),
    ],
    'Nursery 2': [
        ('Maths', 4000),
        ('English', 4000),
        ('Colouring / H.W', 4500),
        ('Q/V', 6000),
        ('Exercise Books (10)', 5000),
    ],
}


def seed_additional_books(apps, schema_editor):
    ClassRoom = apps.get_model('portal', 'ClassRoom')
    BookItem = apps.get_model('portal', 'BookItem')

    for classroom_name, items in BOOK_DATA.items():
        classroom = (
            ClassRoom.objects.filter(name__iexact=classroom_name).first()
            or ClassRoom.objects.filter(name__icontains=classroom_name).first()
        )
        if not classroom:
            continue
        for title, price in items:
            BookItem.objects.update_or_create(
                target_class=classroom,
                title=title,
                defaults={'price': price},
            )


def unseed_additional_books(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0073_populate_initial_books'),
    ]

    operations = [
        migrations.RunPython(seed_additional_books, unseed_additional_books),
    ]

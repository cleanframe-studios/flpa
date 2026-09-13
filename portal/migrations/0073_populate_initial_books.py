from django.db import migrations

BOOK_DATA = {
    'Nursery 1': [
        ('Maths', 4000),
        ('English', 4000),
        ('Colouring / H.W', 4500),
        ('Q/V', 6000),
        ('Exercise Books (10)', 5000),
    ],
    'KG 2': [
        ('Maths', 3500),
        ('English', 3500),
        ('Colouring / H.W', 4000),
        ('Exercise Books (10)', 5000),
    ],
    'Primary 1': [
        ('English', 5000),
        ('Maths', 5000),
        ('Q/V', 6000),
        ('Mental Maths', 4500),
        ('English Skills', 4500),
        ('Composition', 5000),
        ('Novels (3)', 3000),
        ('Exercise Books (20)', 10000),
    ],
    'Primary 6': [
        ('English', 5000),
        ('Maths', 5000),
        ('Q/V', 6000),
        ('Mental Maths', 4500),
        ('English Skills', 4500),
        ('Composition', 5000),
        ('Novels (3)', 3000),
        ('Exercise Books (20)', 10000),
        ('Past Questions', 7000),
    ],
}
for name in ('Primary 2', 'Primary 3', 'Primary 4'):
    BOOK_DATA[name] = BOOK_DATA['Primary 1']


def seed_books(apps, schema_editor):
    ClassRoom = apps.get_model('portal', 'ClassRoom')
    BookItem = apps.get_model('portal', 'BookItem')

    for classroom_name, items in BOOK_DATA.items():
        classroom = (
            ClassRoom.objects.filter(name__iexact=classroom_name).first()
            or ClassRoom.objects.filter(name__icontains=classroom_name).first()
        )
        if not classroom and 'Primary' in classroom_name:
            alt_name = classroom_name.replace('Primary', 'Basic')
            classroom = (
                ClassRoom.objects.filter(name__iexact=alt_name).first()
                or ClassRoom.objects.filter(name__icontains=alt_name).first()
            )
        if not classroom:
            continue
        for title, price in items:
            BookItem.objects.update_or_create(
                target_class=classroom,
                title=title,
                defaults={'price': price},
            )


def unseed_books(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0072_delete_feeitem'),
    ]

    operations = [
        migrations.RunPython(seed_books, unseed_books),
    ]

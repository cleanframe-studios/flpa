"""Seed the BookItem book list with the exact prices provided by the school (WhatsApp price lists)."""
from django.core.management.base import BaseCommand
from portal.models import ClassRoom, BookItem


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
# Basic 1-4 share the same list as Primary 1
for classroom_name in ('Primary 2', 'Primary 3', 'Primary 4'):
    BOOK_DATA[classroom_name] = BOOK_DATA['Primary 1']


class Command(BaseCommand):
    help = 'Seed BookItem records with the school-provided book list prices per class.'

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0
        skipped_classes = []
        for classroom_name, items in BOOK_DATA.items():
            classroom = ClassRoom.objects.filter(name=classroom_name).first()
            if not classroom:
                skipped_classes.append(classroom_name)
                continue
            for title, price in items:
                obj, created = BookItem.objects.update_or_create(
                    target_class=classroom,
                    title=title,
                    defaults={'price': price},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1
        self.stdout.write(self.style.SUCCESS(
            f'Book list seeded: {created_count} created, {updated_count} updated.'
        ))
        if skipped_classes:
            self.stdout.write(self.style.WARNING(
                f'Classes not found in database (skipped): {", ".join(skipped_classes)}'
            ))

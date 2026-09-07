from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0063_applicant_accepted_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicant',
            name='other_name',
            field=models.CharField(blank=True, max_length=50),
        ),
    ]

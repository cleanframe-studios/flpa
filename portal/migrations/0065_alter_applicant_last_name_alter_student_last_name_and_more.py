from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0064_applicant_other_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='applicant',
            name='last_name',
            field=models.CharField(max_length=50, verbose_name='Surname'),
        ),
        migrations.AlterField(
            model_name='student',
            name='last_name',
            field=models.CharField(max_length=50, verbose_name='Surname'),
        ),
        migrations.AlterField(
            model_name='teacher',
            name='last_name',
            field=models.CharField(max_length=50, verbose_name='Surname'),
        ),
    ]

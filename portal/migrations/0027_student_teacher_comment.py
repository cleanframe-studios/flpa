from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0026_student_lin'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='teacher_comment',
            field=models.TextField(blank=True, default=''),
        ),
    ]
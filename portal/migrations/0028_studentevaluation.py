from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0027_student_teacher_comment'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentEvaluation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attentiveness', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('punctuality', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('self_control', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('relationship_with_others', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('music', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('indoor_games', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('outdoor_games', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('club_association', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluations', to='portal.student')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='student_evaluations', to='portal.academicterm')),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('student', 'term'), name='unique_student_term_evaluation')]},
        ),
    ]
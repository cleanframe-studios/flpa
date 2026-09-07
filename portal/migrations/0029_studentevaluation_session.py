from django.db import migrations, models
import django.db.models.deletion


def backfill_sessions(apps, schema_editor):
    StudentEvaluation = apps.get_model('portal', 'StudentEvaluation')
    for evaluation in StudentEvaluation.objects.select_related('term'):
        evaluation.session_id = evaluation.term.session_id
        evaluation.save(update_fields=['session'])


class Migration(migrations.Migration):
    dependencies = [('portal', '0028_studentevaluation')]

    operations = [
        migrations.RemoveConstraint(
            model_name='studentevaluation',
            name='unique_student_term_evaluation',
        ),
        migrations.AddField(
            model_name='studentevaluation',
            name='session',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='student_evaluations', to='portal.academicsession'),
        ),
        migrations.RunPython(backfill_sessions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='studentevaluation',
            name='session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='student_evaluations', to='portal.academicsession'),
        ),
        migrations.AddConstraint(
            model_name='studentevaluation',
            constraint=models.UniqueConstraint(fields=('student', 'session', 'term'), name='unique_student_session_term_evaluation'),
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0061_term_salary_profiles_and_admission_religion'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffsalaryprofile',
            name='allowances',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='staffsalaryprofile',
            name='deductions',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='payrollrun',
            name='academic_session',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payroll_runs', to='portal.academicsession'),
        ),
        migrations.AddField(
            model_name='payrollrun',
            name='academic_term',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payroll_runs', to='portal.academicterm'),
        ),
    ]

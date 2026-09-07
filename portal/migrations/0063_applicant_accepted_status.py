from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0062_staffsalaryprofile_allowances_and_deductions_payrollrun_session_term'),
    ]

    operations = [
        migrations.AlterField(
            model_name='applicant',
            name='admission_status',
            field=models.CharField(choices=[('Pending', 'Pending'), ('Verified', 'Verified'), ('Approved', 'Approved'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected')], default='Pending', max_length=10),
        ),
    ]

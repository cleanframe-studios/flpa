from django.db import migrations, models
import django.db.models.deletion


def assign_legacy_salary_profiles(apps, schema_editor):
    AcademicSession = apps.get_model('portal', 'AcademicSession')
    AcademicTerm = apps.get_model('portal', 'AcademicTerm')
    StaffSalaryProfile = apps.get_model('portal', 'StaffSalaryProfile')

    session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.order_by('-name').first()
    if not session:
        session = AcademicSession.objects.create(name='Legacy Salary Session')
    term = AcademicTerm.objects.filter(session=session, is_active=True).first() or AcademicTerm.objects.filter(session=session).first()
    if not term:
        term = AcademicTerm.objects.create(session=session, term_name='First Term')
    StaffSalaryProfile.objects.filter(academic_session__isnull=True).update(academic_session=session, academic_term=term)


def deduplicate_parent_phones(apps, schema_editor):
    Parent = apps.get_model('portal', 'Parent')
    seen_phones = set()
    for parent in Parent.objects.order_by('pk'):
        phone = parent.phone_number or ''
        if phone not in seen_phones:
            seen_phones.add(phone)
            continue
        suffix = f'DUP{parent.pk}'
        parent.phone_number = f'{phone[:20 - len(suffix)]}{suffix}'
        parent.save(update_fields=['phone_number'])


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0060_alter_applicant_admission_status'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='student',
            name='home_address',
        ),
        migrations.AddField(
            model_name='applicant',
            name='religion',
            field=models.CharField(blank=True, choices=[('Christianity', 'Christianity'), ('Islam', 'Islam'), ('Other', 'Other')], max_length=30),
        ),
        migrations.AlterField(
            model_name='student',
            name='religion',
            field=models.CharField(blank=True, choices=[('Christianity', 'Christianity'), ('Islam', 'Islam'), ('Other', 'Other')], max_length=30, null=True),
        ),
        migrations.RunPython(deduplicate_parent_phones, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='parent',
            name='phone_number',
            field=models.CharField(max_length=20, unique=True),
        ),
        migrations.AddField(
            model_name='staffsalaryprofile',
            name='academic_session',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='salary_profiles', to='portal.academicsession'),
        ),
        migrations.AddField(
            model_name='staffsalaryprofile',
            name='academic_term',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='salary_profiles', to='portal.academicterm'),
        ),
        migrations.AlterField(
            model_name='staffsalaryprofile',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='salary_profiles', to='auth.user'),
        ),
        migrations.RunPython(assign_legacy_salary_profiles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='staffsalaryprofile',
            name='academic_session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='salary_profiles', to='portal.academicsession'),
        ),
        migrations.AlterField(
            model_name='staffsalaryprofile',
            name='academic_term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='salary_profiles', to='portal.academicterm'),
        ),
        migrations.AddConstraint(
            model_name='staffsalaryprofile',
            constraint=models.UniqueConstraint(fields=('user', 'academic_session', 'academic_term'), name='unique_staff_salary_profile_per_term'),
        ),
    ]
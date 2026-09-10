import json
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.urls import reverse
from django.contrib.auth import authenticate, login
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.conf import settings
from django.core.mail import EmailMessage
from smtplib import SMTPException
from django.views.decorators.http import require_POST
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
import datetime
from urllib.parse import quote
from decimal import Decimal, InvalidOperation
from .templatetags.portal_extras import is_cbt_eligible_class
from .models import (
    AcademicSession,
    AcademicTerm,
    AcademicWeek,
    Attendance,
    AttendanceRegister,
    Holiday,
    Student,
    Parent,
    Teacher,
    TeacherQualification,
    TermEnrollment,
    ClassRoom,
    Subject,
    ClassRoomSubject,
    AccountProfile,
    CBTExam,
    CBTQuestion,
    StudentExamSession,
    CBTAttempt,
    CBTResponse,
    SubjectResult,
    StudentEvaluation,
    StudentTermRecord,
    SessionRolloverRecord,
    FeeStructure,
    StudentFeeAccount,
    FeePayment,
    SchoolPaymentAccount,
    AutomatedCommentBank,
    ClassResultStatus,
    AuditLog,
    AdmissionCampaign,
    Applicant,
    Message,
    MessageRecipient,
    Notification,
    StaffSalaryProfile,
    PayrollRun,
    Payslip,
    PushSubscription,
)
from django.db.models import Case, When, Value, IntegerField, Q, Max, Min, Exists, OuterRef, Sum, Avg, F
from .decorators import bursar_required, registrar_required, role_required, teacher_required, principal_required
from .utils import log_security_action, send_registration_email, send_admission_approval_email

User = get_user_model()


def create_portal_account(record, role, password_seed):
    identifier = getattr(record, 'student_id', None) or getattr(record, 'staff_id', None) or getattr(record, 'parent_id', None)
    if not identifier:
        return
    user, _ = User.objects.get_or_create(username=identifier)
    user.set_password((password_seed or identifier).strip().lower())
    user.save(update_fields=['password'])
    record.user = user
    record.save(update_fields=['user'])
    AccountProfile.objects.update_or_create(user=user, defaults={'role': role})

@login_required(login_url='login')
def academic_calendar_view(request):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    active_session = AcademicSession.objects.filter(is_active=True).first()
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_session':
            name = request.POST.get('name', '').strip()
            if name and not AcademicSession.objects.filter(name__iexact=name).exists():
                AcademicSession.objects.create(name=name, is_active=False)
                messages.success(request, 'Academic session created successfully.')
            elif AcademicSession.objects.filter(name__iexact=name).exists():
                messages.error(request, 'This Academic Session has already been created.')
            else:
                messages.error(request, 'Please select an academic session.')
        elif action == 'set_session_active':
            session = get_object_or_404(AcademicSession, pk=request.POST['session'])
            session.is_active = request.POST.get('value') == '1'
            session.save()
        elif action == 'create_term':
            session_id = request.POST.get('session')
            term_name = request.POST.get('term_name', '').strip()
            if session_id and term_name and not AcademicTerm.objects.filter(session_id=session_id, term_name__iexact=term_name).exists():
                AcademicTerm.objects.create(session_id=session_id, term_name=term_name, is_active=False)
                messages.success(request, 'Academic term created successfully.')
            elif AcademicTerm.objects.filter(session_id=session_id, term_name__iexact=term_name).exists():
                messages.error(request, 'This academic term already exists.')
            else:
                messages.error(request, 'Please select a unique session and term name.')
        elif action == 'set_term_active':
            term = get_object_or_404(AcademicTerm, pk=request.POST['term'])
            term.is_active = request.POST.get('value') == '1'
            term.save()
        elif action == 'create_holiday':
            date_value = parse_date(request.POST.get('date'))
            term_id = request.POST.get('term')
            description = request.POST.get('description', '').strip()
            if term_id and date_value and description:
                Holiday.objects.create(term_id=term_id, date=date_value, description=description)
        elif action == 'generate_weeks':
            term_id = request.POST.get('term')
            monday = parse_date(request.POST.get('start_date') or '')
            if not term_id or not monday:
                messages.error(request, 'Please select both an active term and a starting date.')
            else:
                term = get_object_or_404(AcademicTerm, pk=term_id)
                if term.weeks.exists():
                    messages.error(request, 'The 15 weeks have already been generated for this term.')
                elif monday.weekday() != 0:
                    messages.error(request, 'Week generation must start on a Monday.')
                else:
                    AcademicWeek.objects.bulk_create([AcademicWeek(term=term, week_number=i, start_date=monday + datetime.timedelta(days=(i - 1) * 7), end_date=monday + datetime.timedelta(days=(i - 1) * 7 + 4)) for i in range(1, 16)])
                    messages.success(request, 'Fifteen academic weeks generated successfully.')
        elif action == 'delete_weeks':
            if principal_action_denied(request):
                return redirect('academic_calendar')
            deleted_count, _ = AcademicWeek.objects.filter(term_id=request.POST.get('term')).delete()
            if deleted_count:
                messages.success(request, f'{deleted_count} generated academic weeks deleted successfully.')
            else:
                messages.warning(request, 'There are no generated weeks to delete for this term.')
        return redirect('academic_calendar')
    selected_term = AcademicTerm.objects.filter(is_active=True).select_related('session').first()
    terms = AcademicTerm.objects.filter(session=active_session).select_related('session') if active_session else AcademicTerm.objects.none()
    return render(request, 'portal/academic_calendar.html', {
        'sessions': AcademicSession.objects.all(),
        'session_choices': ['2026/2027', '2027/2028', '2028/2029', '2029/2030'],
        'active_session': active_session,
        'selected_term': selected_term,
        'terms': terms,
        'active_terms': AcademicTerm.objects.filter(is_active=True).select_related('session'),
        'holidays': Holiday.objects.select_related('term').all(),
        'weeks': selected_term.weeks.all() if selected_term else [],
    })


@login_required(login_url='login')
@registrar_required
def term_enrollment_view(request):
    active_term = AcademicTerm.objects.filter(is_active=True).select_related('session').first()
    if request.method == 'POST' and active_term:
        active_students = Student.objects.filter(status__in=('Active', 'Student'), current_class__isnull=False)
        created_count = 0
        updated_count = 0
        try:
            with transaction.atomic():
                for student in active_students:
                    _, created = TermEnrollment.objects.update_or_create(
                        student=student,
                        term=active_term,
                        defaults={'classroom': student.current_class},
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1
        except IntegrityError:
            messages.error(request, f'Enrollment could not be completed for {active_term} because of a duplicate or data conflict.')
        else:
            if created_count or updated_count:
                messages.success(request, f'{created_count} active student(s) enrolled and {updated_count} enrollment(s) synchronized for {active_term}.')
            else:
                messages.warning(request, f'No active students with classroom assignments were found for {active_term}.')
        return redirect('term_enrollment')
    return render(request, 'portal/term_enrollment.html', {
        'active_term': active_term,
        'enrollments': TermEnrollment.objects.filter(
            term=active_term,
            student__status__in=('Active', 'Student'),
        ).select_related('student', 'classroom') if active_term else [],
    })


@login_required(login_url='login')
def class_subjects_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_subject':
            classroom = get_object_or_404(ClassRoom, pk=request.POST.get('classroom'))
            subject_name = request.POST.get('subject_name', '').strip()
            if not subject_name:
                messages.error(request, 'Please enter a subject name.')
            else:
                subject, _ = Subject.objects.get_or_create(name=subject_name)
                assignment, created = ClassRoomSubject.objects.get_or_create(class_room=classroom, subject=subject)
                if created:
                    messages.success(request, f'{subject.name} assigned to {classroom.name}.')
                else:
                    messages.warning(request, f'{subject.name} is already assigned to {classroom.name}.')
            return redirect('class_subjects')
        if action == 'edit_subject':
            subject = get_object_or_404(Subject, pk=request.POST.get('subject'))
            subject_name = request.POST.get('subject_name', '').strip()
            if not subject_name:
                messages.error(request, 'Please enter a subject name.')
            elif Subject.objects.filter(name=subject_name).exclude(pk=subject.pk).exists():
                messages.error(request, 'That subject name is already in use.')
            else:
                subject.name = subject_name
                subject.save(update_fields=['name'])
                messages.success(request, 'Subject updated successfully.')
            return redirect('class_subjects')
        if action == 'delete_subject':
            if principal_action_denied(request):
                return redirect('class_subjects')
            subject = get_object_or_404(Subject, pk=request.POST.get('subject'))
            subject_name = subject.name
            subject.delete()
            messages.success(request, f'{subject_name} removed from the master subject list and all class assignments.')
            return redirect('class_subjects')
        return redirect('class_subjects')

    return render(request, 'portal/class_subjects.html', {
        'classrooms': ClassRoom.objects.prefetch_related('class_subjects__subject').order_by('section', 'level_number', 'name'),
        'subjects': Subject.objects.prefetch_related('classroomsubject_set').order_by('name'),
    })


@login_required(login_url='login')
def manage_classes_view(request):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    if request.method == 'POST':
        classroom = get_object_or_404(ClassRoom, pk=request.POST.get('classroom_id'))
        is_terminal = request.POST.get('is_terminal') == '1'
        if is_terminal:
            classroom.next_class = None
            classroom.is_terminal = True
            classroom.save(update_fields=['next_class', 'is_terminal'])
            messages.success(request, f'{classroom.name} progression settings saved.')
        else:
            next_class_id = request.POST.get('next_class') or None
            if next_class_id and str(next_class_id) == str(classroom.pk):
                messages.error(request, 'A class cannot progress to itself.')
            else:
                next_class = get_object_or_404(ClassRoom, pk=next_class_id) if next_class_id else None
                classroom.next_class = next_class
                classroom.is_terminal = False
                classroom.save(update_fields=['next_class', 'is_terminal'])
                messages.success(request, f'{classroom.name} progression settings saved.')
        return redirect('manage_classes')
    return render(request, 'portal/manage_classes.html', {
        'classrooms': ClassRoom.objects.select_related('next_class').order_by('sequence', 'section', 'level_number', 'name'),
        'all_classrooms': ClassRoom.objects.order_by('sequence', 'section', 'level_number', 'name'),
    })

def public_home_view(request):
    now = timezone.now()
    AdmissionCampaign.objects.filter(status='Active', deadline__lt=now).update(status='Closed', is_active=False)
    landing_campaign = AdmissionCampaign.objects.filter(status__in=['Active', 'Closed']).select_related(
        'target_session',
        'target_term',
    ).order_by(
        Case(When(status='Active', then=Value(0)), default=Value(1), output_field=IntegerField()),
        '-deadline',
    ).first()
    return render(request, 'portal/public_home.html', {'landing_campaign': landing_campaign})


def about_page(request):
    return render(request, 'portal/about_page.html')


def gallery_page(request):
    gallery_images = [
        {'src': 'portal/exu_1.jpg', 'caption': 'Excursions · New perspectives'},
        {'src': 'portal/exu_2.jpg', 'caption': 'Excursions · Learning beyond the classroom'},
        {'src': 'portal/exu_3.jpg', 'caption': 'Excursions · Shared discovery'},
        {'src': 'portal/cul_1.jpg', 'caption': 'Cultural Day · Celebrating heritage'},
        {'src': 'portal/cul_2.jpg', 'caption': 'Cultural Day · Colour and community'},
        {'src': 'portal/cul_3.jpg', 'caption': 'Cultural Day · Expression and joy'},
        {'src': 'portal/awa_1.jpg', 'caption': 'Awards · Celebrating excellence'},
        {'src': 'portal/awa_2.jpg', 'caption': 'Awards · Proud achievements'},
        {'src': 'portal/act_1.jpg', 'caption': 'Activities · Growing together'},
    ]
    return render(request, 'portal/gallery_page.html', {'gallery_images': gallery_images})


def contact_page(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        message = request.POST.get('message', '').strip()
        try:
            if email:
                validate_email(email)
            enquiry = EmailMessage(
                subject=f'Website enquiry from {name}',
                body=f'Name: {name}\nEmail: {email or "Not provided"}\n\nMessage:\n{message}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.CONTACT_EMAIL],
                reply_to=[email] if email else [],
            )
            enquiry.send(fail_silently=False)
        except (ValidationError, SMTPException):
            messages.error(request, 'We could not send your enquiry right now. Please try again or contact us directly by email.')
        else:
            messages.success(request, 'Thank you. Your enquiry has been sent and our team will be in touch.')
    return render(request, 'portal/contact_page.html')


def _login_destination(user):
    if hasattr(user, 'account_profile'):
        if user.account_profile.role == 'student' and hasattr(user, 'student_record'):
            return 'student_dashboard'
        if user.account_profile.role == 'teacher' and hasattr(user, 'teacher_record'):
            return 'teacher_dashboard'
        if user.account_profile.role == 'parent' and hasattr(user, 'parent_record'):
            return 'parent_dashboard'
    return 'dashboard'


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_login_destination(request.user))

    if request.method == 'POST':
        user_name = request.POST.get('username')
        pass_word = request.POST.get('password')
        remember_me = request.POST.get('remember_me') == 'on'
        
        user = authenticate(request, username=user_name, password=pass_word)
        
        if user is not None:
            student = getattr(user, 'student_record', None)
            if student and not student.has_portal_access:
                messages.warning(request, 'Login access is restricted to Primary 4 and above.')
                return redirect('login')
            login(request, user)
            request.session.set_expiry(settings.SESSION_COOKIE_AGE if remember_me else 0)
            return redirect(_login_destination(user))
        else:
            messages.error(request, 'Invalid username or password.')

    now = timezone.now()
    AdmissionCampaign.objects.filter(status='Active', deadline__lt=now).update(status='Closed', is_active=False)
    landing_campaign = AdmissionCampaign.objects.filter(status__in=['Active', 'Closed']).select_related(
        'target_session',
        'target_term',
    ).order_by(
        Case(When(status='Active', then=Value(0)), default=Value(1), output_field=IntegerField()),
        '-deadline',
    ).first()
    return render(request, 'portal/login.html', {'landing_campaign': landing_campaign})


def logout_view(request):
    logout(request)
    return redirect('login')


def apply_admission_view(request):
    campaign = AdmissionCampaign.objects.filter(status='Active', deadline__gte=timezone.now()).select_related('target_session', 'target_term').first()
    if not campaign:
        messages.error(request, 'There is no open admission campaign at this time.')
        return redirect('login')
    classrooms = ClassRoom.objects.order_by('section', 'sequence', 'name')
    payment_account = SchoolPaymentAccount.objects.filter(is_active=True).first()
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        other_name = request.POST.get('other_name', '').strip()
        date_of_birth = request.POST.get('date_of_birth') or None
        sex = request.POST.get('sex', '')
        nationality = request.POST.get('nationality', '').strip() or 'Nigerian'
        religion = request.POST.get('religion', '').strip()
        state_of_origin = request.POST.get('state_of_origin', '').strip()
        lga = request.POST.get('lga', '').strip()
        has_disability = request.POST.get('has_disability') == '1'
        disability_details = request.POST.get('disability_details', '').strip()
        school_type = request.POST.get('school_type', '')
        previous_school = request.POST.get('previous_school', '').strip()
        present_class = request.POST.get('present_class', '').strip()
        programme_of_study = request.POST.get('programme_of_study', '')
        intended_class_id = request.POST.get('intended_class')
        father_name = request.POST.get('father_name', '').strip()
        father_occupation = request.POST.get('father_occupation', '').strip()
        father_job_title = request.POST.get('father_job_title', '').strip()
        father_phone = request.POST.get('father_phone', '').strip()
        father_email = request.POST.get('father_email', '').strip()
        father_address = request.POST.get('father_address', '').strip()
        mother_name = request.POST.get('mother_name', '').strip()
        mother_occupation = request.POST.get('mother_occupation', '').strip()
        mother_job_title = request.POST.get('mother_job_title', '').strip()
        mother_phone = request.POST.get('mother_phone', '').strip()
        mother_email = request.POST.get('mother_email', '').strip()
        mother_address = request.POST.get('mother_address', '').strip()
        next_of_kin_name = request.POST.get('next_of_kin_name', '').strip()
        next_of_kin_relationship = request.POST.get('next_of_kin_relationship', '').strip()
        next_of_kin_phone = request.POST.get('next_of_kin_phone', '').strip()
        parent_email = request.POST.get('parent_email', '').strip()
        passport = request.FILES.get('passport')

        intended_class = ClassRoom.objects.filter(pk=intended_class_id).first()
        parent_name = father_name or mother_name
        parent_phone = father_phone or mother_phone

        errors = []
        if not (first_name and last_name and other_name and date_of_birth and sex):
            errors.append('Please complete all basic applicant details.')
        if not intended_class:
            errors.append('Please select a valid intended class.')
        if not (father_name or mother_name):
            errors.append('Please provide at least one parent/guardian name.')
        if not (father_phone or mother_phone):
            errors.append('Please provide at least one parent/guardian phone number.')
        submitted_parent_phones = [phone for phone in (father_phone, mother_phone) if phone]
        duplicate_parent_phone = Parent.objects.filter(phone_number__in=submitted_parent_phones).values_list('phone_number', flat=True).first()
        duplicate_application_phone = Applicant.objects.filter(
            Q(parent_phone__in=submitted_parent_phones) | Q(father_phone__in=submitted_parent_phones) | Q(mother_phone__in=submitted_parent_phones)
        ).values_list('parent_phone', flat=True).first()
        if duplicate_parent_phone:
            errors.append(f'The phone number {duplicate_parent_phone} is already registered. Please provide a different number.')
        elif duplicate_application_phone:
            errors.append('A parent phone number is already linked to another admission application. Please provide a different number.')
        if parent_email:
            try:
                validate_email(parent_email)
            except ValidationError:
                errors.append('Please provide a valid email address.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'portal/apply_admission.html', {
                'campaign': campaign,
                'classrooms': classrooms,
                'form_data': request.POST,
                'program_choices': Student.PROGRAM_CHOICES,
                'school_type_choices': Applicant.SCHOOL_TYPE_CHOICES,
                'payment_account': payment_account,
            })

        applicant = Applicant.objects.create(
            campaign=campaign,
            first_name=first_name,
            last_name=last_name,
            other_name=other_name,
            date_of_birth=date_of_birth,
            sex=sex,
            nationality=nationality,
            religion=religion,
            state_of_origin=state_of_origin,
            lga=lga,
            passport=passport,
            has_disability=has_disability,
            disability_details=disability_details,
            school_type=school_type,
            previous_school=previous_school,
            present_class=present_class,
            programme_of_study=programme_of_study,
            intended_class=intended_class,
            parent_name=parent_name,
            parent_phone=parent_phone,
            parent_email=parent_email,
            father_name=father_name,
            father_occupation=father_occupation,
            father_job_title=father_job_title,
            father_phone=father_phone,
            father_email=father_email or None,
            father_address=father_address,
            mother_name=mother_name,
            mother_occupation=mother_occupation,
            mother_job_title=mother_job_title,
            mother_phone=mother_phone,
            mother_email=mother_email or None,
            mother_address=mother_address,
            next_of_kin_name=next_of_kin_name,
            next_of_kin_relationship=next_of_kin_relationship,
            next_of_kin_phone=next_of_kin_phone,
        )
        if not send_registration_email(applicant):
            messages.warning(request, 'Application saved, but we could not send the confirmation email. Please note your Registration Number below.')
        return redirect('admission_payment', temp_reg_number=applicant.temp_reg_number)
    return render(request, 'portal/apply_admission.html', {
        'campaign': campaign,
        'classrooms': classrooms,
        'program_choices': Student.PROGRAM_CHOICES,
        'school_type_choices': Applicant.SCHOOL_TYPE_CHOICES,
        'payment_account': payment_account,
    })


def admission_payment_view(request, temp_reg_number):
    applicant = get_object_or_404(
        Applicant.objects.select_related('campaign'),
        temp_reg_number__iexact=temp_reg_number,
    )
    receipt_message = (
        f'Hello Admin, I have paid the admission application fee for {applicant.first_name} '
        f'{applicant.other_name} {applicant.last_name}. Registration number: {applicant.temp_reg_number}. '
        f'Please verify my payment.'
    )
    whatsapp_url = f'https://wa.me/2347063747789?text={quote(" ".join(receipt_message.split()))}'
    return render(request, 'portal/admission_payment.html', {'applicant': applicant, 'whatsapp_url': whatsapp_url})


@require_POST
def admission_status_lookup_view(request):
    try:
        temp_reg_number = request.POST.get('temp_reg_number', '').strip().upper()
        applicant = Applicant.objects.select_related('campaign__target_session', 'campaign__target_term', 'intended_class').filter(temp_reg_number__iexact=temp_reg_number).first()
        if not applicant:
            return JsonResponse({'found': False, 'message': 'No application was found for that registration number.'}, status=404)
        if getattr(applicant, 'is_accepted', False) or str(applicant.admission_status).upper() == 'ACCEPTED':
            return JsonResponse({
                'found': True,
                'already_accepted': True,
                'message': 'Admission already accepted! Please log in normally with your assigned credentials.',
                'applicant': {
                    'name': f'{applicant.first_name} {applicant.last_name}',
                    'registration_number': applicant.temp_reg_number,
                    'admission_status': applicant.admission_status,
                },
            })
        response = {
            'found': True,
            'applicant': {
                'name': f'{applicant.first_name} {applicant.last_name}',
                'registration_number': applicant.temp_reg_number,
                'intended_class': applicant.intended_class.name,
                'session': applicant.campaign.target_session.name,
                'term': applicant.campaign.target_term.term_name,
                'payment_status': applicant.payment_status,
                'admission_status': applicant.admission_status,
            },
        }
        if applicant.admission_status == 'Approved':
            father_missing_fields = admission_profile_gaps(applicant, 'father')
            mother_missing_fields = admission_profile_gaps(applicant, 'mother')
            response['onboarding'] = {
                'missing_fields': father_missing_fields,
                'parent_missing_fields': {
                    'father': father_missing_fields,
                    'mother': mother_missing_fields,
                },
                'ready': not father_missing_fields and not mother_missing_fields,
            }
        return JsonResponse(response)
    except Exception:
        return JsonResponse({'found': False, 'message': 'Unable to look up this application right now.'}, status=500)


def _selected_guardian_details(applicant, parent_choice=None):
    use_mother = parent_choice == 'mother'
    return {
        'name': (applicant.mother_name if use_mother else applicant.father_name) or applicant.parent_name,
        'phone': (applicant.mother_phone if use_mother else applicant.father_phone) or applicant.parent_phone,
        'email': (applicant.mother_email if use_mother else applicant.father_email) or applicant.parent_email,
        'address': (applicant.mother_address if use_mother else applicant.father_address),
        'occupation': applicant.mother_occupation if use_mother else applicant.father_occupation,
        'sex': 'Female' if use_mother else 'Male',
    }


def admission_profile_gaps(applicant, parent_choice=None):
    guardian = _selected_guardian_details(applicant, parent_choice)
    field_values = {
        'guardian_name': guardian['name'],
        'guardian_phone': guardian['phone'],
        'guardian_address': guardian['address'],
        'state_of_origin': applicant.state_of_origin,
        'lga': applicant.lga,
    }
    labels = {
        'guardian_name': 'Parent or guardian full name',
        'guardian_phone': 'Parent or guardian phone number',
        'guardian_address': 'Parent or guardian home address',
        'state_of_origin': 'State of origin',
        'lga': 'LGA of origin',
    }
    return [{'name': name, 'label': labels[name], 'type': 'email' if name == 'guardian_email' else 'text'} for name, value in field_values.items() if not value]


def provision_admission_accounts(applicant, parent_choice=None):
    if applicant.admission_status != 'Approved' or admission_profile_gaps(applicant, parent_choice):
        return None, None
    guardian = _selected_guardian_details(applicant, parent_choice)
    guardian_name = guardian['name']
    guardian_phone = guardian['phone']
    guardian_email = guardian['email']
    guardian_address = guardian['address']
    name_parts = guardian_name.split(maxsplit=1)
    parent = applicant.provisioned_parent
    if not parent:
        parent = Parent.objects.create(
            first_name=name_parts[0],
            last_name=name_parts[1] if len(name_parts) > 1 else applicant.last_name,
            phone_number=guardian_phone,
            sex=guardian['sex'],
            email=guardian_email,
            occupation=guardian['occupation'],
            marital_status='Married',
            address=guardian_address,
            state=applicant.state_of_origin,
            lga=applicant.lga,
            status='Active',
        )
    student = applicant.enrolled_student
    if not student:
        program = {'KG': 'Kindergarten (KG)', 'Nursery': 'Nursery (NUR)', 'Primary': 'Primary (PRY)'}.get(applicant.intended_class.section, 'Primary (PRY)')
        student = Student.objects.create(
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            other_name=applicant.other_name,
            sex=applicant.sex or 'Male',
            date_of_birth=applicant.date_of_birth or timezone.localdate(),
            state_of_origin=applicant.state_of_origin or 'Not provided',
            lga_of_origin=applicant.lga or 'Not provided',
            program=program,
            current_class=applicant.intended_class,
            passport=applicant.passport if applicant.passport else None,
            phone_number=applicant.parent_phone,
            email=applicant.parent_email or '',
            religion=applicant.religion or None,
            status='Student',
            parent=parent,
        )
    if student.parent_id != parent.pk:
        student.parent = parent
        student.save(update_fields=['parent'])
    if applicant.provisioned_parent_id != parent.pk:
        applicant.provisioned_parent = parent
    applicant.parent_id = parent.parent_id
    if applicant.enrolled_student_id != student.pk:
        applicant.enrolled_student = student
    applicant.student_id = student.student_id
    applicant.save(update_fields=['provisioned_parent', 'enrolled_student', 'parent_id', 'student_id'])
    create_portal_account(student, 'student', student.last_name)
    create_portal_account(parent, 'parent', parent.last_name or parent.first_name)
    return student, parent


@require_POST
def admission_complete_profile_view(request):
    try:
        applicant = Applicant.objects.select_related('intended_class').filter(temp_reg_number__iexact=request.POST.get('temp_reg_number', '').strip()).first()
        if not applicant:
            return JsonResponse({'status': 'error', 'success': False, 'message': 'No application was found for that registration number.'}, status=404)
        if applicant.admission_status != 'Approved':
            return JsonResponse({'status': 'error', 'success': False, 'message': 'Profile completion is available after admission approval.'}, status=400)
        parent_choice = request.POST.get('parent_choice')
        if parent_choice not in ('mother', 'father'):
            return JsonResponse({'status': 'error', 'success': False, 'message': 'Select the parent for the primary profile.'}, status=400)
        values = {
        'guardian_name': request.POST.get('guardian_name', '').strip(),
        'guardian_phone': request.POST.get('guardian_phone', '').strip(),
        'guardian_email': request.POST.get('guardian_email', '').strip(),
        'guardian_address': request.POST.get('guardian_address', '').strip(),
        'state_of_origin': request.POST.get('state_of_origin', '').strip(),
        'lga': request.POST.get('lga', '').strip(),
        }
        with transaction.atomic():
            if values['guardian_name']:
                applicant.parent_name = values['guardian_name']
                setattr(applicant, f'{parent_choice}_name', values['guardian_name'])
            if values['guardian_phone']:
                applicant.parent_phone = values['guardian_phone']
                setattr(applicant, f'{parent_choice}_phone', values['guardian_phone'])
            if values['guardian_email']:
                applicant.parent_email = values['guardian_email']
                setattr(applicant, f'{parent_choice}_email', values['guardian_email'])
            if values['guardian_address']:
                setattr(applicant, f'{parent_choice}_address', values['guardian_address'])
            for field in ('state_of_origin', 'lga'):
                if values[field]:
                    setattr(applicant, field, values[field])
            applicant.save()
            missing_fields = admission_profile_gaps(applicant, parent_choice)
            if missing_fields:
                return JsonResponse({'status': 'error', 'success': False, 'missing_fields': missing_fields}, status=400)
            student, parent = provision_admission_accounts(applicant, parent_choice)
            if not student or not parent:
                raise ValidationError('Unable to provision the admission accounts.')
            applicant.admission_status = 'Accepted'
            applicant.save()
            credentials = [
                {'role': 'parent', 'username': parent.parent_id, 'password': (parent.last_name or parent.first_name).strip().lower(), 'portal_url': request.build_absolute_uri(reverse('login'))},
            ]
            if student.has_portal_access:
                credentials.insert(0, {'role': 'student', 'username': student.student_id, 'password': student.last_name.strip().lower(), 'portal_url': request.build_absolute_uri(reverse('login'))})
            return JsonResponse({'status': 'success', 'success': True, 'credentials': [
                *credentials,
            ]})
    except Exception as error:
        return JsonResponse({'status': 'error', 'success': False, 'message': str(error) or 'Unable to create portal accounts.'}, status=500)


@require_POST
def admission_credentials_view(request):
    applicant = Applicant.objects.filter(temp_reg_number__iexact=request.POST.get('temp_reg_number', '').strip()).first()
    if not applicant:
        return JsonResponse({'success': False, 'message': 'No application was found for that registration number.'}, status=404)
    parent_choice = request.POST.get('parent_choice')
    if parent_choice not in ('mother', 'father'):
        return JsonResponse({'success': False, 'message': 'Select the parent for the primary profile.'}, status=400)
    student, parent = applicant.enrolled_student, applicant.provisioned_parent
    if not student or not parent:
        return JsonResponse({'success': False, 'message': 'Complete the profile before viewing login details.'}, status=400)
    return JsonResponse({
        'success': True,
        'student': {
            'id': student.student_id,
            'password': student.last_name.strip().lower() if student.current_class and student.current_class.section == 'Primary' and student.current_class.level_number >= 4 else None,
        },
        'parent': {'id': parent.parent_id, 'password': (parent.last_name or parent.first_name).strip().lower()},
    })


@login_required(login_url='login')
@registrar_required
def admissions_hub_view(request):
    now = timezone.now()
    AdmissionCampaign.objects.filter(status='Active', deadline__lt=now).update(status='Closed', is_active=False)
    campaigns = AdmissionCampaign.objects.select_related('target_session', 'target_term').all()
    applicants = Applicant.objects.select_related('campaign', 'intended_class')
    return render(request, 'portal/admissions_hub.html', {
        'active_campaign': campaigns.filter(status='Active', deadline__gte=now).first(),
        'total_campaigns': campaigns.count(),
        'pending_applicants': applicants.filter(admission_status='Pending').count(),
        'verified_unapproved': applicants.filter(payment_status='Verified', admission_status='Pending').count(),
        'approved_count': applicants.filter(admission_status='Approved').count(),
        'recent_applicants': applicants.order_by('-submitted_at')[:5],
    })


@login_required(login_url='login')
@registrar_required
def manage_campaigns_view(request):
    AdmissionCampaign.objects.filter(status='Active', deadline__lt=timezone.now()).update(status='Closed', is_active=False)

    def combined_deadline():
        deadline_date = parse_date(request.POST.get('deadline_date') or '')
        if not deadline_date:
            return None
        deadline_time = request.POST.get('deadline_time') or '23:59'
        hour, _, minute = deadline_time.partition(':')
        naive = datetime.datetime.combine(deadline_date, datetime.time(int(hour or 0), int(minute or 0)))
        return timezone.make_aware(naive)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_campaign':
            AdmissionCampaign.objects.create(
                campaign_name=request.POST.get('campaign_name', '').strip(),
                target_session_id=request.POST.get('target_session'),
                target_term_id=request.POST.get('target_term'),
                application_fee=request.POST.get('application_fee') or 0,
                deadline=combined_deadline(),
                status=request.POST.get('status', 'Closed'),
            )
            messages.success(request, 'Admission campaign created.')
        elif action == 'edit_campaign':
            campaign = get_object_or_404(AdmissionCampaign, pk=request.POST.get('campaign_id'))
            campaign.campaign_name = request.POST.get('campaign_name', '').strip()
            campaign.target_session_id = request.POST.get('target_session')
            campaign.target_term_id = request.POST.get('target_term')
            campaign.application_fee = request.POST.get('application_fee') or 0
            campaign.deadline = combined_deadline()
            campaign.status = 'Closed' if campaign.deadline and campaign.deadline < timezone.now() else request.POST.get('status', 'Closed')
            campaign.is_active = campaign.status == 'Active'
            campaign.save()
            messages.success(request, 'Admission campaign updated.')
        elif action == 'close_campaign':
            campaign = get_object_or_404(AdmissionCampaign, pk=request.POST.get('campaign_id'))
            campaign.status = 'Closed'
            campaign.is_active = False
            campaign.save()
            messages.success(request, 'Admission campaign closed.')
        return redirect('manage_campaigns')
    terms_data = {}
    for session in AcademicSession.objects.all():
        terms_data[str(session.id)] = list(session.terms.values('id', 'term_name'))
    return render(request, 'portal/manage_campaigns.html', {
        'campaigns': AdmissionCampaign.objects.select_related('target_session', 'target_term'),
        'sessions': AcademicSession.objects.order_by('-name'),
        'terms_json': json.dumps(terms_data),
    })


@login_required(login_url='login')
@registrar_required
def review_applicants_view(request):
    if request.method == 'POST':
        applicant = get_object_or_404(
            Applicant.objects.select_related('enrolled_student__parent', 'enrolled_student__user', 'provisioned_parent__user'),
            pk=request.POST.get('applicant_id'),
        )
        action = request.POST.get('action')
        if action == 'verify_payment':
            applicant.payment_status = 'Verified'
            applicant.save(update_fields=['payment_status'])
            messages.success(request, f'Payment verified for {applicant.temp_reg_number}.')
        elif action == 'reject':
            applicant.admission_status = 'Rejected'
            applicant.save(update_fields=['admission_status'])
            messages.success(request, f'Application {applicant.temp_reg_number} rejected.')
        elif action == 'approve_enroll':
            if applicant.admission_status not in ('Pending', 'Verified'):
                messages.error(request, 'Only pending or verified applicants can be approved.')
            elif applicant.payment_status != 'Verified':
                messages.error(request, 'Verify payment before approving this applicant.')
            else:
                applicant.admission_status = 'Approved'
                applicant.save(update_fields=['admission_status'])
                messages.success(request, f'Application {applicant.temp_reg_number} approved. Accounts will be created when the applicant accepts admission.')
        return redirect('review_applicants')
    return render(request, 'portal/review_applicants.html', {
        'applicants': Applicant.objects.select_related('campaign', 'intended_class', 'enrolled_student'),
    })


@require_POST
@login_required(login_url='login')
@registrar_required
def revoke_admission_view(request, pk):
    if principal_action_denied(request):
        return JsonResponse({'success': False, 'message': 'This sensitive action is restricted to administrators.'}, status=403)
    applicant = get_object_or_404(
        Applicant.objects.select_related('enrolled_student__user', 'provisioned_parent__user'),
        pk=pk,
        admission_status='Approved',
    )
    student = applicant.enrolled_student
    parent = applicant.provisioned_parent
    with transaction.atomic():
        if student:
            student_user = student.user if hasattr(student, 'user') else None
            student.delete()
            if student_user:
                student_user.delete()
        if parent:
            parent_user = parent.user if hasattr(parent, 'user') else None
            parent.delete()
            if parent_user:
                parent_user.delete()
        applicant.enrolled_student = None
        applicant.provisioned_parent = None
        applicant.student_id = ''
        applicant.parent_id = ''
        applicant.admission_status = 'Verified'
        applicant.save(update_fields=['enrolled_student', 'provisioned_parent', 'student_id', 'parent_id', 'admission_status'])
    return JsonResponse({'success': True, 'message': 'Admission approval was revoked. Generated student and parent profiles were removed.'})


@login_required(login_url='login')
@registrar_required
def admission_print_view(request, pk):
    applicant = get_object_or_404(Applicant.objects.select_related('campaign', 'intended_class', 'enrolled_student'), pk=pk)
    return render(request, 'portal/admission_print.html', {'applicant': applicant})


def _staff_recipient_users():
    staff_roles = ('admin', 'principal', 'bursar', 'teacher', 'registrar')
    return User.objects.filter(
        is_active=True,
        is_superuser=False,
        account_profile__role__in=staff_roles,
    ).distinct()


def _parent_recipient_users(classroom=None):
    students = Student.objects.filter(status='Student', parent__isnull=False, parent__user__isnull=False)
    if classroom:
        students = students.filter(current_class=classroom)
    return User.objects.filter(
        pk__in=students.values_list('parent__user_id', flat=True),
        is_active=True,
        is_superuser=False,
        account_profile__role='parent',
    ).distinct()


def _primary_login_classrooms():
    return ClassRoom.objects.filter(section='Primary', level_number__gte=4).order_by('level_number', 'name')


def _send_message(sender, subject, body, priority, recipient_users):
    recipient_users = list(recipient_users)
    message = Message.objects.create(sender=sender, subject=subject, body=body, priority=priority)
    MessageRecipient.objects.bulk_create([
        MessageRecipient(message=message, recipient_user=user) for user in recipient_users
    ], ignore_conflicts=True)
    Notification.objects.bulk_create([
        Notification(recipient=user, title=subject, message=body, link=reverse('inbox'))
        for user in recipient_users
    ])
    return message


def _notify_users(recipient_users, title, message, link=''):
    Notification.objects.bulk_create([
        Notification(recipient=user, title=title, message=message, link=link)
        for user in recipient_users
    ])


@login_required(login_url='login')
def notification_view(request, pk):
    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return redirect(notification.link or 'dashboard')


@login_required(login_url='login')
@role_required(['Admin', 'Principal'])
def general_messaging_view(request):
    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        body = request.POST.get('body', '').strip()
        priority = request.POST.get('priority', 'Standard')
        audience = request.POST.get('audience')
        if not subject or not body:
            messages.error(request, 'Please provide a subject and message body.')
        else:
            if audience == 'staff':
                staff_user_id = request.POST.get('recipient_user')
                recipients = _staff_recipient_users() if staff_user_id in ('', 'all_staff', None) else _staff_recipient_users().filter(pk=staff_user_id)
            elif audience == 'parent':
                parent_user_id = request.POST.get('recipient_user')
                if parent_user_id in ('', 'all_parents', None):
                    recipients = _parent_recipient_users()
                elif parent_user_id.startswith('class_parents_'):
                    classroom_id = parent_user_id.removeprefix('class_parents_')
                    classroom = ClassRoom.objects.filter(pk=classroom_id, section='Primary', level_number__gte=4).first()
                    recipients = _parent_recipient_users(classroom) if classroom else User.objects.none()
                elif parent_user_id.startswith('parent_id_'):
                    recipients = _parent_recipient_users().filter(pk=parent_user_id.removeprefix('parent_id_'))
                else:
                    recipients = User.objects.none()
            elif audience == 'class':
                classroom = ClassRoom.objects.filter(pk=request.POST.get('classroom')).first()
                recipients = _parent_recipient_users(classroom) if classroom else User.objects.none()
            else:
                recipients = User.objects.none()
            recipients = recipients.exclude(pk=request.user.pk)
            _send_message(request.user, subject, body, priority, recipients)
            messages.success(request, f'Message broadcast to {recipients.count()} recipient(s).')
            return redirect('general_messaging')
    staff_users = _staff_recipient_users().select_related('teacher_record').order_by('first_name', 'last_name', 'username')
    parent_users = _parent_recipient_users().select_related('parent_record').order_by('parent_record__first_name', 'parent_record__last_name', 'username')
    parent_options = [{'pk': 'all_parents', 'name': 'All Parents', 'option_type': 'broadcast'}]
    parent_options += [
        {'pk': f'class_parents_{classroom.pk}', 'name': f'Parents of {classroom.name}', 'option_type': 'class_group'}
        for classroom in _primary_login_classrooms()
    ]
    parent_options += [
        {
            'pk': f'parent_id_{user.pk}',
            'name': f'{getattr(user.parent_record, "display_name", user.username)} ({user.username})',
            'option_type': 'individual',
        }
        for user in parent_users
    ]
    return render(request, 'portal/general_messaging.html', {
        'classrooms': _primary_login_classrooms(),
        'audience_options': [
            {'pk': 'staff', 'name': 'Staff'},
            {'pk': 'parent', 'name': 'Parent'},
            {'pk': 'class', 'name': 'Class'},
        ],
        'staff_options': [{'pk': 'all_staff', 'name': 'All Staff'}] + [
            {
                'pk': user.pk,
                'name': (
                    ' '.join(
                        part for part in (
                            getattr(getattr(user, 'teacher_record', None), 'first_name', ''),
                            getattr(getattr(user, 'teacher_record', None), 'other_name', ''),
                            getattr(getattr(user, 'teacher_record', None), 'last_name', ''),
                        ) if part
                    ).strip()
                    or user.get_full_name()
                    or user.username
                ),
            }
            for user in staff_users
        ],
        'parent_options': parent_options,
        'priority_choices': Message.PRIORITY_CHOICES,
        'sent_messages': Message.objects.filter(sender=request.user).order_by('-timestamp')[:10],
    })


@login_required(login_url='login')
@role_required(['Admin', 'Principal'])
def result_messaging_view(request):
    if request.method == 'POST':
        classroom = get_object_or_404(ClassRoom, pk=request.POST.get('classroom'))
        term = get_object_or_404(AcademicTerm, pk=request.POST.get('term'))
        recipients = _parent_recipient_users(classroom).exclude(pk=request.user.pk)
        subject = f"Report Card Published - {classroom.name}"
        body = f"The report card for {classroom.name} ({term.term_name}, {term.session.name}) has been published. Please log in to the parent portal to view your child's results."
        _send_message(request.user, subject, body, 'Important', recipients)
        messages.success(request, f'Result notification sent to {recipients.count()} parent(s).')
        return redirect('result_messaging')
    sessions = AcademicSession.objects.order_by('-name')
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else (active_term.session if active_term else None)
    terms = AcademicTerm.objects.select_related('session').filter(session=selected_session).order_by('start_date') if selected_session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else (terms.filter(pk=active_term.pk).first() if active_term and selected_session == active_term.session else terms.first())
    classrooms = ClassRoom.objects.order_by('section', 'sequence', 'name')
    selected_classroom = classrooms.filter(pk=request.GET.get('classroom')).first() if request.GET.get('classroom') else None
    published_statuses = ClassResultStatus.objects.filter(is_published=True).select_related('classroom', 'term', 'term__session').order_by('-term__start_date')
    if selected_session:
        published_statuses = published_statuses.filter(term__session=selected_session)
    if selected_term:
        published_statuses = published_statuses.filter(term=selected_term)
    if selected_classroom:
        published_statuses = published_statuses.filter(classroom=selected_classroom)
    return render(request, 'portal/result_messaging.html', {
        'sessions': sessions,
        'classrooms': classrooms,
        'terms': terms,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'selected_classroom': selected_classroom,
        'terms_json': json.dumps(session_terms_map()),
        'published_statuses': published_statuses,
    })


@login_required(login_url='login')
def inbox_view(request):
    if request.method == 'GET':
        MessageRecipient.objects.filter(recipient_user=request.user, is_read=False).update(is_read=True)
        Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'mark_read':
            recipient = get_object_or_404(MessageRecipient, pk=request.POST.get('recipient_id'), recipient_user=request.user)
            recipient.is_read = True
            recipient.save(update_fields=['is_read'])
        elif action == 'mark_all_read':
            MessageRecipient.objects.filter(recipient_user=request.user, is_read=False).update(is_read=True)
        return redirect('inbox')
    recipients = MessageRecipient.objects.filter(
        recipient_user=request.user,
        message__timestamp__gte=request.user.date_joined,
    ).select_related('message', 'message__sender').order_by('-message__timestamp')
    return render(request, 'portal/inbox.html', {'recipients': recipients})


@login_required(login_url='login')
def notification_feed_view(request):
    notifications = Notification.objects.filter(
        recipient=request.user,
        created_at__gte=request.user.date_joined,
        is_read=False,
    ).order_by('created_at')[:10]
    return JsonResponse({
        'notifications': [{
            'id': notification.pk,
            'title': notification.title,
            'message': notification.message,
            'link': notification.link or reverse('inbox'),
        } for notification in notifications],
    })


MONTH_CHOICES = PayrollRun.MONTH_CHOICES


@login_required(login_url='login')
@bursar_required
def salary_profiles_view(request):
    raw_session = request.POST.get('session') or request.GET.get('session')
    session_id = raw_session if raw_session and str(raw_session).isdigit() else None
    selected_session = AcademicSession.objects.filter(pk=session_id).first() if session_id else None
    if not selected_session:
        selected_session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.order_by('-name').first()
    terms = AcademicTerm.objects.filter(session=selected_session).order_by('start_date', 'pk') if selected_session else AcademicTerm.objects.none()
    raw_term = request.POST.get('term') or request.GET.get('term')
    term_id = raw_term if raw_term and str(raw_term).isdigit() else None
    selected_term = terms.filter(pk=term_id).first() if term_id else None
    if not selected_term:
        selected_term = terms.filter(is_active=True).first() or terms.first()

    if request.method == 'POST':
        action = request.POST.get('action', 'save_profile')
        if not selected_session or not selected_term:
            messages.error(request, 'Select an academic session and term before configuring salary profiles.')
        elif action == 'fetch_previous_term':
            term_order = Case(
                When(term_name='First Term', then=Value(1)),
                When(term_name='Second Term', then=Value(2)),
                When(term_name='Third Term', then=Value(3)),
                default=Value(99),
                output_field=IntegerField(),
            )
            ordered_terms = list(AcademicTerm.objects.select_related('session').annotate(term_order=term_order).order_by('session__name', 'term_order', 'pk'))
            previous_term = ordered_terms[ordered_terms.index(selected_term) - 1] if selected_term in ordered_terms and ordered_terms.index(selected_term) else None
            if not previous_term:
                messages.error(request, 'There is no previous term to copy from.')
            else:
                previous_profiles = StaffSalaryProfile.objects.filter(academic_term=previous_term).select_related('user')
                copied = 0
                for profile in previous_profiles:
                    _, created = StaffSalaryProfile.objects.get_or_create(
                        user=profile.user,
                        academic_session=selected_session,
                        academic_term=selected_term,
                        defaults={
                            'base_salary': profile.base_salary,
                            'allowances': profile.allowances,
                            'deductions': profile.deductions,
                            'bank_name': profile.bank_name,
                            'account_number': profile.account_number,
                            'is_active': profile.is_active,
                        },
                    )
                    copied += int(created)
                messages.success(request, f'Copied {copied} salary profile(s) from {previous_term.session.name} {previous_term.term_name}.')
        else:
            user = get_object_or_404(staff_role_users(), pk=request.POST.get('user_id'))
            if action == 'clear_profile':
                if principal_action_denied(request):
                    return redirect('salary_profiles')
                try:
                    StaffSalaryProfile.objects.filter(pk=request.POST.get('profile_id'), user=user, academic_term=selected_term).delete()
                except ProtectedError:
                    messages.error(request, 'Cannot modify or clear this profile because payroll has already been processed for this term. Please revert the payroll run first.')
                else:
                    messages.success(request, f'Salary profile cleared for {user.get_full_name() or user.username}.')
            else:
                profile, _ = StaffSalaryProfile.objects.get_or_create(
                    user=user,
                    academic_session=selected_session,
                    academic_term=selected_term,
                )
                profile.academic_session = selected_session
                profile.academic_term = selected_term
                profile.base_salary = request.POST.get('base_salary') or 0
                profile.allowances = request.POST.get('allowances') or 0
                profile.deductions = request.POST.get('deductions') or 0
                profile.housing_allowance = 0
                profile.transport_allowance = 0
                profile.tax_deduction = 0
                profile.pension_deduction = 0
                profile.bank_name = request.POST.get('bank_name', '').strip()
                profile.account_number = request.POST.get('account_number', '').strip()
                profile.is_active = request.POST.get('is_active') == '1'
                profile.full_clean()
                profile.save()
                messages.success(request, f'Salary profile saved for {user.get_full_name() or user.username}.')
        return redirect(f"{reverse('salary_profiles')}?session={selected_session.pk}&term={selected_term.pk}" if selected_session and selected_term else 'salary_profiles')
    configured_profiles = StaffSalaryProfile.objects.filter(academic_session=selected_session, academic_term=selected_term).select_related('user', 'user__teacher_record').order_by('user__username') if selected_term else StaffSalaryProfile.objects.none()
    profiles_by_user = {profile.user_id: profile for profile in configured_profiles}
    staff_users = staff_role_users().select_related('teacher_record', 'account_profile').prefetch_related('groups').order_by('username')
    for staff_user in staff_users:
        staff_user.selected_salary_profile = profiles_by_user.get(staff_user.pk)
    total_salary = sum((profile.base_salary for profile in configured_profiles), Decimal('0'))
    terms_json = {
        str(session.pk): list(session.terms.values('id', 'term_name'))
        for session in AcademicSession.objects.all()
    }
    return render(request, 'portal/salary_profiles.html', {
        'staff_users': staff_users,
        'configured_profiles': configured_profiles,
        'sessions': AcademicSession.objects.order_by('-name'),
        'terms': terms,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'selected_session_id': selected_session.pk if selected_session else '',
        'selected_term_id': selected_term.pk if selected_term else '',
        'total_salary': total_salary,
        'terms_json': json.dumps(terms_json),
    })


@login_required(login_url='login')
@bursar_required
def run_payroll_view(request):
    today = timezone.localdate()
    selected_month = int(request.POST.get('month') or request.GET.get('month') or today.month)
    selected_year = int(request.POST.get('year') or request.GET.get('year') or today.year)
    existing_run = PayrollRun.objects.filter(month=selected_month, year=selected_year).first()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'process_payroll':
            if existing_run:
                messages.error(request, 'A payroll run already exists for this month/year.')
            else:
                active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
                active_profiles = StaffSalaryProfile.objects.filter(is_active=True, academic_term=active_term).select_related('user')
                if not active_profiles.exists():
                    messages.error(request, 'There are no active staff salary profiles to process.')
                else:
                    with transaction.atomic():
                        run = PayrollRun.objects.create(
                            month=selected_month,
                            year=selected_year,
                            academic_session=active_term.session,
                            academic_term=active_term,
                            processed_by=request.user,
                        )
                        total_gross = Decimal('0')
                        total_net = Decimal('0')
                        for profile in active_profiles:
                            gross = profile.gross_pay
                            deductions = profile.total_deductions
                            net = profile.net_pay
                            Payslip.objects.create(
                                salary_profile=profile,
                                payroll_run=run,
                                gross_pay=gross,
                                total_deductions=deductions,
                                net_pay=net,
                            )
                            total_gross += gross
                            total_net += net
                        run.total_gross = total_gross
                        run.total_net = total_net
                        run.save(update_fields=['total_gross', 'total_net'])
                        log_security_action(request, 'PAYROLL_PROCESSED', f'Payroll {selected_month:02d}/{selected_year}', {
                            'after': {'staff_count': active_profiles.count(), 'total_net': str(total_net)},
                        })
                    messages.success(request, f'Payroll processed for {active_profiles.count()} staff member(s).')
                    existing_run = run
        elif action == 'revert_run':
            if principal_action_denied(request):
                return redirect('run_payroll')
            run = get_object_or_404(
                PayrollRun,
                pk=request.POST.get('run_id'),
                academic_session_id=request.POST.get('session_id'),
                academic_term_id=request.POST.get('term_id'),
            )
            if run.status != 'Draft':
                messages.error(request, 'Only pending payroll runs can be reverted.')
            else:
                with transaction.atomic():
                    run.delete()
                messages.success(request, 'Payroll processing reverted. Salary profiles can now be modified.')
            existing_run = PayrollRun.objects.filter(month=selected_month, year=selected_year).first()
        elif action == 'approve_run':
            run = get_object_or_404(PayrollRun, pk=request.POST.get('run_id'))
            if run.status != 'Draft':
                messages.error(request, 'Only draft payroll runs can be approved.')
            else:
                previous_status = run.status
                run.status = 'Approved'
                run.save(update_fields=['status'])
                log_security_action(request, 'PAYROLL_APPROVED', f'Payroll {run.month:02d}/{run.year}', {
                    'before': {'status': previous_status}, 'after': {'status': run.status},
                })
                messages.success(request, 'Payroll run approved.')
            existing_run = run
        elif action == 'disburse_run':
            run = get_object_or_404(PayrollRun, pk=request.POST.get('run_id'))
            if run.status != 'Approved':
                messages.error(request, 'Only approved payroll runs can be disbursed.')
            else:
                previous_status = run.status
                run.status = 'Disbursed'
                run.save(update_fields=['status'])
                run.payslips.update(is_disbursed=True)
                log_security_action(request, 'PAYROLL_DISBURSED', f'Payroll {run.month:02d}/{run.year}', {
                    'before': {'status': previous_status}, 'after': {'status': run.status},
                })
                messages.success(request, 'Payroll run disbursed to staff.')
            existing_run = run

    active_term = AcademicTerm.objects.filter(is_active=True).first()
    active_profiles = StaffSalaryProfile.objects.filter(is_active=True, academic_term=active_term).select_related('user')
    preview_total_gross = sum((profile.gross_pay for profile in active_profiles), Decimal('0'))
    preview_total_net = sum((profile.net_pay for profile in active_profiles), Decimal('0'))
    return render(request, 'portal/run_payroll.html', {
        'month_choices': MONTH_CHOICES,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'active_profiles': active_profiles,
        'preview_total_gross': preview_total_gross,
        'preview_total_net': preview_total_net,
        'existing_run': existing_run,
        'existing_run_payslips': existing_run.payslips.select_related('salary_profile__user') if existing_run else None,
        'years': range(today.year - 2, today.year + 2),
    })


@login_required(login_url='login')
@bursar_required
def payroll_history_view(request):
    runs = PayrollRun.objects.select_related('processed_by', 'academic_session', 'academic_term').prefetch_related('payslips__salary_profile__user')
    sessions = AcademicSession.objects.order_by('-name')
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else None
    terms = AcademicTerm.objects.filter(session=selected_session).order_by('start_date', 'pk') if selected_session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else None
    if selected_session:
        runs = runs.filter(academic_session=selected_session)
    if selected_term:
        runs = runs.filter(academic_term=selected_term)
    return render(request, 'portal/payroll_history.html', {
        'runs': runs,
        'sessions': sessions,
        'terms': terms,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'terms_json': json.dumps(session_terms_map()),
    })


@login_required(login_url='login')
def staff_my_payslips_view(request):
    profiles = request.user.salary_profiles.all()
    profile = profiles.first()
    payslips = Payslip.objects.filter(salary_profile__in=profiles).select_related('payroll_run')
    return render(request, 'portal/staff_my_payslips.html', {'profile': profile, 'payslips': payslips})


def is_basic_exam_student(student):
    class_name = (student.current_class.name if student.current_class else '').lower()
    return any(term in class_name for term in ('primary 4', 'basic 4', 'primary 6', 'basic 6'))


@login_required(login_url='login')
def student_dashboard_view(request):
    student = getattr(request.user, 'student_record', None)
    if not student:
        return redirect('dashboard')
    latest_promotion_record = student.term_records.filter(
        term__term_name='Third Term',
    ).select_related('term__session').order_by('-term__session__name', '-pk').first()
    promotion_notice = None
    if latest_promotion_record and not latest_promotion_record.promotion_notice_dismissed:
        if student.status == 'Graduated':
            promotion_notice = {'status': 'Graduated'}
        elif latest_promotion_record.promotion_status == 'Promoted' and student.current_class:
            promotion_notice = {'status': 'Promoted', 'next_class_name': student.current_class.name}
        elif latest_promotion_record.promotion_status == 'Repeated' and student.current_class:
            promotion_notice = {'status': 'Repeated', 'current_class_name': student.current_class.name}
    completed_sessions = StudentExamSession.objects.filter(
        student=student,
        exam=OuterRef('pk'),
        is_completed=True,
    )
    exams = CBTExam.objects.filter(
        classroom=student.current_class,
        is_active=True,
        end_time__gte=timezone.now(),
    ).annotate(attempted=Exists(completed_sessions)).filter(attempted=False) if is_basic_exam_student(student) else CBTExam.objects.none()
    return render(request, 'portal/student_dashboard.html', {
        'student': student,
        'exams': exams,
        'cbt_eligible': is_basic_exam_student(student),
        'student_class': student.current_class,
        'student_lin': student.lin,
        'latest_promotion_record': latest_promotion_record,
        'promotion_notice': promotion_notice,
    })


@login_required(login_url='login')
def dismiss_promotion_notice_view(request):
    student = getattr(request.user, 'student_record', None)
    if not student:
        return redirect('dashboard')
    latest_promotion_record = student.term_records.filter(
        term__term_name='Third Term',
    ).order_by('-term__session__name', '-pk').first()
    if latest_promotion_record and not latest_promotion_record.promotion_notice_dismissed:
        latest_promotion_record.promotion_notice_dismissed = True
        latest_promotion_record.save(update_fields=['promotion_notice_dismissed'])
    return redirect('student_report_hub')


@login_required(login_url='login')
def cbt_center_view(request):
    student = getattr(request.user, 'student_record', None)
    if not student or not is_basic_exam_student(student):
        return redirect('dashboard')
    completed_sessions = StudentExamSession.objects.filter(student=student, exam=OuterRef('pk'), is_completed=True)
    exams = CBTExam.objects.filter(classroom=student.current_class, is_active=True, start_time__lte=timezone.now(), end_time__gte=timezone.now()).select_related('subject').annotate(attempted=Exists(completed_sessions))
    return render(request, 'portal/cbt_center.html', {'student': student, 'exams': exams})


@login_required(login_url='login')
def teacher_dashboard_view(request):
    teacher = getattr(request.user, 'teacher_record', None)
    if not teacher:
        return redirect('dashboard')
    classes = teacher.assigned_class.all()
    return render(request, 'portal/teacher_dashboard.html', {
        'teacher': teacher,
        'classes': classes,
        'active_students': Student.objects.filter(status='Student', current_class__in=classes).count(),
        'subjects': Subject.objects.order_by('name'),
    })


@login_required(login_url='login')
def parent_dashboard_view(request):
    parent = getattr(request.user, 'parent_record', None)
    if not parent:
        return redirect('dashboard')
    active_term = AcademicTerm.objects.filter(is_active=True).first()
    children = list(parent.children.select_related('current_class'))
    attendance_data = Attendance.objects.filter(
        student__in=children,
    ).select_related('student', 'classroom', 'session').order_by('-date', 'student__last_name')[:100]
    for child in children:
        child.recent_attendance = child.attendance.filter(date__gte=timezone.localdate() - datetime.timedelta(days=6)).order_by('-date')[:5]
        child.fee_account = StudentFeeAccount.objects.filter(student=child, term=active_term, session=active_term.session).first() if active_term else None
        child.outstanding_balance = student_outstanding_balance(child, active_term)
        child.is_cleared = child.outstanding_balance <= 0
    return render(request, 'portal/parent_dashboard.html', {
        'parent': parent,
        'children': children,
        'attendance_data': attendance_data,
        'active_term': active_term,
        'payment_channels': [
            ('School Fees', 'Zenith Bank', '1223688239', 'Future Leaders Private Academy'),
            ('Books / Uniform', 'Providus Bank', '6507146199', 'Funmilayo Fasina'),
        ],
    })


@login_required(login_url='login')
def parent_results_view(request):
    parent = getattr(request.user, 'parent_record', None)
    if not parent:
        return redirect('dashboard')
    return redirect('student_report_hub')


def _parent_published_results(request, template_name):
    parent = getattr(request.user, 'parent_record', None)
    if not parent:
        return redirect('dashboard')
    term = AcademicTerm.objects.filter(is_active=True).first()
    children = list(parent.children.select_related('current_class'))
    for child in children:
        publication = ClassResultStatus.objects.filter(
            classroom=child.current_class,
            term=term,
        ).first() if term and child.current_class else None
        child.is_published = bool(publication and publication.is_live)
        child.is_cleared = True
        child.fee_account = StudentFeeAccount.objects.filter(
            student=child,
            term=term,
            session=term.session,
        ).first() if term else None
        if child.fee_account:
            child.is_cleared = child.fee_account.is_cleared
        child.results = valid_subject_results(
            SubjectResult.objects.filter(student=child, term=term)
        ).select_related('subject') if child.is_published and child.is_cleared else SubjectResult.objects.none()
    return render(request, template_name, {
        'children': children,
        'term': term,
        'payment_channels': [
            ('School Fees', 'Zenith Bank', '1223688239', 'Future Leaders Private Academy'),
            ('Books / Uniform', 'Providus Bank', '6507146199', 'Funmilayo Fasina'),
        ],
    })


@login_required(login_url='login')
def parent_report_cards_view(request):
    return _parent_published_results(request, 'portal/parent_report_cards.html')


@login_required(login_url='login')
def parent_bursary_view(request):
    parent = getattr(request.user, 'parent_record', None)
    if not parent:
        return redirect('dashboard')
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    children = list(parent.children.select_related('current_class').all())
    for child in children:
        child.fee_accounts_list = list(child.fee_accounts.select_related('term', 'session').prefetch_related('payments').order_by('-term__start_date'))
        child.outstanding_balance = student_outstanding_balance(child, active_term)
        child.is_cleared = child.outstanding_balance <= 0
        for account in child.fee_accounts_list:
            account.is_current_term = bool(active_term and account.term_id == active_term.pk)
            account.is_rollover_debt = bool(not account.is_current_term and account.balance > 0)
    return render(request, 'portal/parent_bursary.html', {
        'children': children,
        'active_term': active_term,
        'payment_channels': [
            ('School Fees', 'Zenith Bank', '1223688239', 'Future Leaders Private Academy'),
            ('Books / Uniform', 'Providus Bank', '6507146199', 'Funmilayo Fasina'),
        ],
    })


def student_outstanding_balance(student, through_term=None):
    accounts = student.fee_accounts.all()
    if through_term:
        ordered_term_ids = list(AcademicTerm.objects.order_by(
            'session__name', 'start_date', 'pk',
        ).values_list('pk', flat=True))
        through_index = ordered_term_ids.index(through_term.pk)
        accounts = accounts.filter(term_id__in=ordered_term_ids[:through_index + 1])
    return sum(
        (max(account.balance, Decimal('0')) for account in accounts),
        Decimal('0'),
    )


def fee_accounts_through(account):
    ordered_accounts = list(StudentFeeAccount.objects.select_for_update().filter(
        student=account.student,
    ).select_related('term', 'session').order_by('session__name', 'term__start_date', 'term_id', 'pk'))
    for index, candidate in enumerate(ordered_accounts):
        if candidate.pk == account.pk:
            return ordered_accounts[:index + 1]
    return []


def apply_fifo_payment(account, amount, recorded_by):
    accounts = fee_accounts_through(account)
    outstanding = sum((max(candidate.balance, Decimal('0')) for candidate in accounts), Decimal('0'))
    if amount > outstanding:
        raise ValueError('Payment exceeds the outstanding balance through the selected term.')
    remaining = amount
    for candidate in accounts:
        allocation = min(max(candidate.balance, Decimal('0')), remaining)
        if allocation <= 0:
            continue
        FeePayment.objects.create(account=candidate, amount=allocation, recorded_by=recorded_by)
        candidate.amount_paid += allocation
        candidate.save(update_fields=['amount_paid', 'is_cleared'])
        remaining -= allocation
    return amount - remaining


def historical_classroom(student, term):
    enrollment = TermEnrollment.objects.select_related('classroom').filter(
        student=student,
        term=term,
    ).first() if term else None
    return enrollment.classroom if enrollment else student.current_class if term and term.is_active else None


def students_in_term_classroom(term, classroom):
    if not term or not classroom:
        return Student.objects.none()
    students = Student.objects.filter(
        term_enrollments__term=term,
        term_enrollments__classroom=classroom,
    )
    if not TermEnrollment.objects.filter(term=term).exists():
        students = Student.objects.filter(subject_results__term=term).distinct()
        if not students.exists() and term.is_active:
            students = Student.objects.filter(current_class=classroom)
    if term.is_active:
        students = students.filter(status__in=('Active', 'Student'))
    return students.order_by('last_name', 'first_name')


def results_are_locked(classroom, term):
    status = ClassResultStatus.objects.filter(classroom=classroom, term=term).first() if classroom and term else None
    return bool(term and (term.broadsheet_approved or term.reports_published or (status and status.is_live)))


def session_terms_map():
    terms_map = {}
    for term in AcademicTerm.objects.order_by('session__name', 'start_date', 'pk'):
        terms_map.setdefault(str(term.session_id), []).append({
            'pk': term.pk,
            'name': term.term_name,
        })
    return terms_map


@login_required(login_url='login')
def student_report_hub(request):
    student = getattr(request.user, 'student_record', None)
    parent = getattr(request.user, 'parent_record', None)
    if student:
        report_students = [student]
    elif parent:
        report_students = list(parent.children.select_related('current_class').all())
    else:
        return redirect('dashboard')
    sessions = AcademicSession.objects.order_by('-name')
    sessions_terms_map = session_terms_map()
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    session_id = request.GET.get('session') or (active_term.session_id if active_term else '')
    term_id = request.GET.get('term') or (active_term.pk if active_term else '')
    selected_session = sessions.filter(pk=session_id).first() if session_id else None
    terms = AcademicTerm.objects.select_related('session').filter(session=selected_session).order_by('start_date') if selected_session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=term_id).first() if term_id else None
    if selected_term is None and session_id == str(active_term.session_id if active_term else '') and active_term:
        selected_term = active_term
    report_cards = []
    for report_student in report_students:
        classroom = historical_classroom(report_student, selected_term)
        class_published = bool(classroom and selected_term and ClassResultStatus.objects.filter(
            classroom=classroom,
            term=selected_term,
            is_published=True,
        ).exists())
        results = valid_subject_results(
            SubjectResult.objects.filter(student=report_student, term=selected_term)
        ).select_related('subject') if selected_term else SubjectResult.objects.none()
        term_record = StudentTermRecord.objects.filter(student=report_student, term=selected_term).first() if selected_term else None
        outstanding_balance = student_outstanding_balance(report_student, selected_term)
        report_cards.append({
            'student': report_student,
            'classroom': classroom,
            'results': results,
            'term_record': term_record,
            'is_published': bool(selected_term and (selected_term.reports_published or class_published)),
            'outstanding_balance': outstanding_balance,
            'is_cleared': outstanding_balance <= 0,
        })
    return render(request, 'portal/student_reports_hub.html', {
        'sessions': sessions,
        'terms': terms,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'selected_session_id': str(session_id),
        'selected_term_id': str(term_id),
        'terms_json': json.dumps(sessions_terms_map),
        'report_cards': report_cards,
    })


def is_admin_user(user):
    profile = getattr(user, 'account_profile', None)
    return (
        user.is_superuser
        or getattr(profile, 'role', '').lower() == 'admin'
        or getattr(profile, 'role', '').lower() == 'principal'
        or user.groups.filter(name__iexact='Admin').exists()
        or user.groups.filter(name__iexact='Principal').exists()
    )


def is_principal_user(user):
    profile = getattr(user, 'account_profile', None)
    profile_role = getattr(profile, 'role', '').lower()
    return (
        not user.is_superuser
        and profile_role != 'admin'
        and not user.groups.filter(name__iexact='Admin').exists()
        and (profile_role == 'principal' or user.groups.filter(name__iexact='Principal').exists())
    )


def principal_action_denied(request):
    if is_principal_user(request.user):
        messages.error(request, 'This sensitive action is restricted to administrators.')
        return True
    return False


def is_finance_user(user):
    return is_admin_user(user) or getattr(getattr(user, 'account_profile', None), 'role', None) == 'bursar'


def can_view_audit_logs(user):
    return is_admin_user(user)


@login_required(login_url='login')
@user_passes_test(can_view_audit_logs, login_url='dashboard')
@role_required(['Admin', 'Principal'])
def admin_audit_logs_view(request):
    logs = AuditLog.objects.select_related('user')
    action_type = request.GET.get('action_type', '')
    user_query = request.GET.get('user', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    if action_type:
        logs = logs.filter(action_type=action_type)
    if user_query:
        logs = logs.filter(user__username__icontains=user_query)
    parsed_start_date = parse_date(start_date) if start_date else None
    parsed_end_date = parse_date(end_date) if end_date else None
    if parsed_start_date:
        logs = logs.filter(timestamp__date__gte=parsed_start_date)
    if parsed_end_date:
        logs = logs.filter(timestamp__date__lte=parsed_end_date)
    page_obj = Paginator(logs, 20).get_page(request.GET.get('page'))
    audit_actions = [{'pk': '', 'name': 'All actions'}] + [
        {'pk': value, 'name': label} for value, label in AuditLog.ACTION_CHOICES
    ]
    audit_users = [
        {'pk': username, 'name': username}
        for username in AuditLog.objects.values_list('user__username', flat=True).distinct().order_by('user__username')
    ]
    audit_users.insert(0, {'pk': '', 'name': 'All actors'})
    selected_action_label = next(
        (action['name'] for action in audit_actions if action['pk'] == action_type),
        action_type,
    )
    return render(request, 'portal/admin_audit_logs.html', {
        'logs': page_obj,
        'page_obj': page_obj,
        'action_choices': audit_actions,
        'audit_users': audit_users,
        'selected_action_type': action_type,
        'selected_action_label': selected_action_label,
        'user_query': user_query,
        'start_date': start_date,
        'end_date': end_date,
    })


def user_role_label(user):
    if user.is_superuser:
        return 'admin'
    if user.groups.filter(name__iexact='Principal').exists():
        return 'principal'
    profile = getattr(user, 'account_profile', None)
    return profile.role if profile else 'unassigned'


def user_assigned_roles(user):
    staff_roles = {value for value, _ in AccountProfile.ROLE_CHOICES if value not in {'parent', 'student'}}
    roles = {name.lower() for name in user.groups.values_list('name', flat=True)}.intersection(staff_roles)
    profile = getattr(user, 'account_profile', None)
    if profile and profile.role in staff_roles:
        roles.add(profile.role)
    if user.is_staff or user.is_superuser:
        roles.add('admin')
    return sorted(roles)


def staff_role_users():
    staff_roles = ('admin', 'principal', 'bursar', 'teacher', 'registrar')
    return User.objects.filter(
        Q(is_staff=True)
        | Q(is_superuser=True)
        | Q(groups__name__in=('Admin', 'Principal', 'Bursar', 'Teacher', 'Registrar'))
        | Q(account_profile__role__in=staff_roles),
    ).exclude(
        Q(account_profile__role__in=('student', 'parent'))
        | Q(username__icontains='profile-debug')
        | Q(username__icontains='tmp_diag'),
    ).distinct()


@login_required(login_url='login')
@role_required(['Admin', 'Principal'])
def admin_user_roles_view(request):
    if request.method == 'POST':
        if principal_action_denied(request):
            return redirect('admin_user_roles')
        target_user = get_object_or_404(staff_role_users(), pk=request.POST.get('user_id'))
        requested_roles = {role.lower() for role in request.POST.getlist('roles')}
        if not requested_roles and request.POST.get('role'):
            requested_roles = {request.POST['role'].lower()}
        staff_roles = {value for value, _ in AccountProfile.ROLE_CHOICES if value not in {'parent', 'student'}}
        if not requested_roles or not requested_roles.issubset(staff_roles):
            messages.error(request, 'Select at least one valid staff role.')
        elif target_user == request.user and not requested_roles.intersection({'admin', 'principal'}):
            messages.error(request, 'You cannot remove your own administrator access.')
        elif target_user.is_superuser:
            messages.error(request, 'Superuser roles cannot be changed from this dashboard.')
        else:
            previous_roles = user_assigned_roles(target_user)
            role_groups = []
            for role in staff_roles:
                group, _ = Group.objects.get_or_create(name=role.title())
                role_groups.append(group)
            target_user.groups.remove(*role_groups)
            target_user.groups.add(*[group for group in role_groups if group.name.lower() in requested_roles])
            primary_role = sorted(requested_roles)[0]
            AccountProfile.objects.update_or_create(user=target_user, defaults={'role': primary_role})
            target_user.is_staff = 'admin' in requested_roles
            target_user.save(update_fields=['is_staff'])
            log_security_action(request, 'ROLE_CHANGED', target_user.username, {
                'before': {'roles': previous_roles},
                'after': {'roles': sorted(requested_roles)},
            })
            messages.success(request, f'Role updated for {target_user.username}.')
        return redirect('admin_user_roles')

    users = list(staff_role_users().select_related('account_profile', 'teacher_record').prefetch_related('groups').order_by('username'))
    for managed_user in users:
        managed_user.assigned_roles = user_assigned_roles(managed_user)
        teacher_profile = getattr(managed_user, 'teacher_record', None)
        managed_user.display_name = f'{teacher_profile.first_name} {teacher_profile.last_name}' if teacher_profile else managed_user.get_full_name() or managed_user.username
        managed_user.staff_id = teacher_profile.staff_id if teacher_profile else ''
        managed_user.staff_identifier = managed_user.staff_id or managed_user.username or 'System staff'
        managed_user.contact_email = teacher_profile.email if teacher_profile else managed_user.email
    return render(request, 'portal/admin_user_roles.html', {
        'users': users,
        'role_choices': AccountProfile.ROLE_CHOICES,
    })


def teacher_eligible_classes(user):
    teacher = getattr(user, 'teacher_record', None)
    if not teacher:
        return ClassRoom.objects.none()
    return teacher.assigned_class.filter(
        Q(name__icontains='Primary 4') | Q(name__icontains='Primary 6') |
        Q(name__icontains='Basic 4') | Q(name__icontains='Basic 6')
    )


def cbt_eligible_classrooms():
    return ClassRoom.objects.filter(
        Q(name__icontains='Primary 4') | Q(name__icontains='Primary 6') |
        Q(name__icontains='Basic 4') | Q(name__icontains='Basic 6')
    )


def cbt_results_eligible_classrooms():
    return cbt_eligible_classrooms()


def teacher_cbt_results_classes(user):
    teacher = getattr(user, 'teacher_record', None)
    return teacher_eligible_classes(user) if teacher else ClassRoom.objects.none()


def can_manage_cbt(user):
    return is_admin_user(user) or teacher_eligible_classes(user).exists()


def cbt_manageable_exams(user):
    exams = CBTExam.objects.exclude(subject__name__icontains='quantitative').exclude(subject__name__icontains='verbal')
    return exams if is_admin_user(user) else exams.filter(classroom__in=teacher_eligible_classes(user))


def valid_subjects(queryset=None):
    queryset = queryset or Subject.objects.all()
    return queryset.exclude(name__icontains='quantitative').exclude(name__icontains='verbal')


def valid_subject_results(queryset=None):
    queryset = queryset or SubjectResult.objects.all()
    return queryset.exclude(subject__name__icontains='quantitative').exclude(subject__name__icontains='verbal')


@login_required(login_url='login')
def admin_cbt_view(request):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    return render(request, 'portal/admin_cbt.html', {'exams': cbt_manageable_exams(request.user)})


@login_required(login_url='login')
def cbt_setup_view(request):
    if not can_manage_cbt(request.user):
        return redirect('dashboard')
    classrooms = cbt_eligible_classrooms() if is_admin_user(request.user) else teacher_eligible_classes(request.user)
    subjects = valid_subjects().order_by('name')
    classroom_subjects_map = {
        classroom.pk: list(
            ClassRoomSubject.objects.filter(class_room=classroom)
            .values_list('subject_id', flat=True)
        )
        for classroom in classrooms
    }
    active_session = AcademicSession.objects.filter(is_active=True).first()
    active_term = AcademicTerm.objects.filter(is_active=True).first()
    session_id = request.GET.get('session') or (active_session.pk if active_session else '')
    term_id = request.GET.get('term') or (active_term.pk if active_term else '')
    selected_class = request.GET.get('classroom', '')
    selected_subject = request.GET.get('subject', '')
    exams = cbt_manageable_exams(request.user).select_related('subject', 'classroom', 'term', 'term__session')
    if session_id:
        exams = exams.filter(term__session_id=session_id)
    if term_id:
        exams = exams.filter(term_id=term_id)
    if selected_class:
        exams = exams.filter(classroom_id=selected_class)
    if selected_subject:
        exams = exams.filter(subject__name__iexact=selected_subject)
    terms = AcademicTerm.objects.select_related('session').order_by('-session_id', 'term_name')
    return render(request, 'portal/cbt_setup.html', {
        'exams': exams,
        'classrooms': classrooms,
        'subjects': subjects,
        'terms': terms,
        'sessions': AcademicSession.objects.order_by('-name'),
        'active_session': active_session,
        'active_term': active_term,
        'selected_session': str(session_id),
        'selected_term': str(term_id),
        'selected_class': selected_class,
        'selected_subject': selected_subject,
        'subjects_json': json.dumps([{'pk': subject.pk, 'name': subject.name} for subject in subjects]),
        'classroom_subjects_map': json.dumps(classroom_subjects_map),
        'exam_filter_data': '[]',
        'is_cbt_admin': is_admin_user(request.user),
    })



@login_required(login_url='login')
def cbt_questions_view(request):
    if not can_manage_cbt(request.user):
        return redirect('dashboard')

    exams = cbt_manageable_exams(request.user).select_related('subject', 'classroom', 'term', 'term__session')
    selected_session = request.GET.get('session')
    selected_term = request.GET.get('term')
    selected_class = request.GET.get('classroom')
    subject_query = (request.GET.get('subject') or '').strip()

    if selected_session:
        exams = exams.filter(term__session_id=selected_session)
    if selected_term:
        exams = exams.filter(term_id=selected_term)
    if selected_class and 'all' not in selected_class.lower():
        exams = exams.filter(classroom_id=selected_class)
    if subject_query:
        exams = exams.filter(subject__name__icontains=subject_query)

    sessions = AcademicSession.objects.order_by('-name')
    terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name')
    classrooms = cbt_eligible_classrooms().order_by('section', 'level_number', 'name') if is_admin_user(request.user) else teacher_eligible_classes(request.user)
    subjects = valid_subjects(Subject.objects.order_by('name'))

    if request.method == 'POST':
        action = request.POST.get('action', 'add_question')
        if action == 'delete_question':
            if principal_action_denied(request):
                return HttpResponseForbidden('This sensitive action is restricted to administrators.')
            question = get_object_or_404(CBTQuestion, pk=request.POST.get('question_id'), exam__in=cbt_manageable_exams(request.user))
            if timezone.now() >= question.exam.start_time:
                message = (
                    'Teachers cannot modify questions for live or completed exams'
                    if not is_admin_user(request.user)
                    else 'Exam is currently live or completed. Please update the exam schedule to upcoming in Exam Setup before modifying questions'
                )
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'ok': False, 'message': message}, status=403)
                return HttpResponseForbidden(message)
            question.delete()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': True, 'question_id': request.POST.get('question_id')})
            return redirect('cbt_questions')

        exam_id = request.POST.get('exam')
        exam = get_object_or_404(cbt_manageable_exams(request.user), pk=exam_id)
        question_id = request.POST.get('question_id')
        question_text = request.POST.get('question_text', '').strip()
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        correct_answer = request.POST.get('correct_answer')
        image = request.FILES.get('image')

        if question_id:
            question = get_object_or_404(CBTQuestion, pk=question_id, exam=exam)
            is_update = True
            if timezone.now() >= exam.start_time:
                message = (
                    'Teachers cannot modify questions for live or completed exams'
                    if not is_admin_user(request.user)
                    else 'Exam is currently live or completed. Please update the exam schedule to upcoming in Exam Setup before modifying questions'
                )
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'ok': False, 'message': message}, status=403)
                return HttpResponseForbidden(message)
        else:
            question = None
            is_update = False

        if exam.questions.count() >= exam.question_limit and not is_update:
            message = f'This exam already has its {exam.question_limit}-question limit.'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'message': message}, status=400)
            messages.error(request, message)
        elif not question_text or not all((option_a, option_b, option_c, option_d)) or correct_answer not in {'A', 'B', 'C', 'D'}:
            message = 'Question text and all four answer options are required.'
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'ok': False, 'message': message}, status=400)
            messages.error(request, message)
        else:
            if not is_update:
                max_order = CBTQuestion.objects.filter(exam=exam).aggregate(Max('order'))['order__max']
                next_order = 1 if max_order is None else max_order + 1
                question = CBTQuestion(exam=exam, order=next_order)
            question.question_text = question_text
            if image:
                question.image = image
            question.option_a = option_a
            question.option_b = option_b
            question.option_c = option_c
            question.option_d = option_d
            question.correct_answer = correct_answer
            question.save()
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'ok': True,
                    'message': 'Question updated.' if is_update else 'Question added to the question bank.',
                    'question': {
                        'id': question.pk,
                        'question_text': question.question_text,
                        'option_a': question.option_a,
                        'option_b': question.option_b,
                        'option_c': question.option_c,
                        'option_d': question.option_d,
                        'correct_answer': question.correct_answer,
                        'image_url': question.image.url if question.image else '',
                    },
                })
            messages.success(request, 'Question updated.' if is_update else 'Question added to the question bank.')
            return redirect(f"{reverse('cbt_questions')}?session={selected_session or ''}&term={selected_term or ''}&classroom={selected_class or ''}&subject={subject_query}")
    exam_question_feed = {}
    for exam in exams:
        exam_question_feed[str(exam.pk)] = [{
            'id': question.pk,
            'question_text': question.question_text,
            'option_a': question.option_a,
            'option_b': question.option_b,
            'option_c': question.option_c,
            'option_d': question.option_d,
            'correct_answer': question.correct_answer,
            'image_url': question.image.url if question.image else '',
        } for question in exam.questions.all()]

    return render(request, 'portal/cbt_questions.html', {
        'exams': exams,
        'sessions': sessions,
        'terms': terms,
        'classrooms': classrooms,
        'subjects': subjects,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'selected_class': selected_class,
        'selected_subject': subject_query,
        'question_count': sum(exam.questions.count() for exam in exams),
        'exam_question_feed': json.dumps(exam_question_feed),
        'is_cbt_admin': is_admin_user(request.user),
    })


@login_required(login_url='login')
def cbt_results_view(request):
    if not can_manage_cbt(request.user):
        return redirect('dashboard')

    if is_admin_user(request.user):
        allowed_classrooms = cbt_results_eligible_classrooms().order_by('section', 'level_number', 'name')
    else:
        teacher = getattr(request.user, 'teacher_record', None)
        if not teacher:
            return redirect('dashboard')
        allowed_classrooms = teacher_cbt_results_classes(request.user)

    exams = CBTExam.objects.filter(classroom__in=allowed_classrooms).exclude(subject__name__icontains='quantitative').exclude(subject__name__icontains='verbal').select_related('subject', 'classroom', 'term', 'term__session').order_by('-start_time')
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    default_session_name = active_term.session.name if active_term and active_term.session else ''
    default_term_name = active_term.term_name if active_term else ''
    selected_session = request.GET.get('session') or request.POST.get('session') or default_session_name
    selected_term = request.GET.get('term') or request.POST.get('term') or default_term_name
    selected_class = request.GET.get('classroom') or request.POST.get('classroom')
    subject_query = (request.GET.get('subject') or request.POST.get('subject') or '').strip()
    selected_term_obj = None
    if selected_term:
        if selected_term.split('(')[0].strip().isdigit():
            selected_term_obj = AcademicTerm.objects.filter(pk=int(selected_term.split('(')[0].strip())).first()
        else:
            selected_term_obj = AcademicTerm.objects.filter(
                session__name__icontains=selected_session.split('(')[0].strip(),
                term_name__iexact=selected_term.split('(')[0].strip(),
            ).first()

    if selected_session:
        # Dropdown labels append "(Section)"/"(Session)" suffixes; strip them before matching.
        clean_session = selected_session.split('(')[0].strip()
        if clean_session.isdigit():
            exams = exams.filter(term__session_id=int(clean_session))
        else:
            exams = exams.filter(term__session__name__icontains=clean_session)
    if selected_term_obj:
        exams = exams.filter(term=selected_term_obj)
    if selected_class:
        clean_class = selected_class.split('(')[0].strip()
        if clean_class.isdigit():
            classroom_id = int(clean_class)
            if not allowed_classrooms.filter(pk=classroom_id).exists():
                exams = exams.none()  # safely clear exams without discarding selected_class for redisplay
            else:
                exams = exams.filter(classroom_id=classroom_id)
        else:
            exams = exams.filter(classroom__name__icontains=clean_class)
            if not is_admin_user(request.user):
                exams = exams.filter(classroom__in=allowed_classrooms)
    if subject_query:
        clean_subject = subject_query.split('(')[0].strip()
        exams = exams.filter(subject__name__icontains=clean_subject)

    # Resolve all target classes before selecting an exam so the roster is never reduced to one class.
    target_classes = allowed_classrooms
    if selected_class and 'all' not in selected_class.lower():
        clean_class = selected_class.split('(')[0].strip()
        if clean_class.isdigit():
            target_classes = allowed_classrooms.filter(pk=int(clean_class))
        else:
            target_classes = allowed_classrooms.filter(name__icontains=clean_class)

    # Resolve the newest matching exam while retaining the full target class roster.
    selected_exam = None
    if exams.exists():
        if subject_query and 'all' not in subject_query.lower():
            clean_subject = subject_query.split('(')[0].strip()
            selected_exam = exams.filter(subject__name__icontains=clean_subject).order_by('-start_time').first()
        else:
            selected_exam = exams.order_by('-start_time').first()
    if not selected_exam and target_classes.exists() and subject_query and 'all' not in subject_query.lower():
        clean_subject = subject_query.split('(')[0].strip()
        selected_exam = CBTExam.objects.filter(
            classroom__in=target_classes,
            subject__name__icontains=clean_subject,
            term=selected_term_obj,
        ).order_by('-start_time').first()
    if not selected_exam and target_classes.exists():
        selected_exam = CBTExam.objects.filter(classroom__in=target_classes).exclude(
            subject__name__icontains='quantitative'
        ).exclude(subject__name__icontains='verbal').filter(term=selected_term_obj).order_by('-start_time').first()
    if selected_exam and not subject_query:
        subject_query = selected_exam.subject.name
    classrooms = allowed_classrooms
    sessions = AcademicSession.objects.order_by('-name')
    terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name')
    subjects = valid_subjects(Subject.objects.order_by('name'))

    if request.method == 'POST' and request.POST.get('action') == 'delete_submission':
        if principal_action_denied(request):
            return HttpResponseForbidden('This sensitive action is restricted to administrators.')
        session = get_object_or_404(
            StudentExamSession,
            pk=request.POST.get('session_id'),
            exam__in=cbt_manageable_exams(request.user),
        )
        attempt = CBTAttempt.objects.filter(exam=session.exam, student=session.student).first()
        if attempt:
            attempt.delete()
        session.delete()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'session_id': request.POST.get('session_id')})
        return redirect(request.path)

    students = []
    submissions = {}
    enrolled_student_ids = TermEnrollment.objects.filter(
        classroom__in=target_classes,
    ).values_list('student_id', flat=True)
    student_queryset = Student.objects.filter(
        Q(current_class__in=target_classes) | Q(pk__in=enrolled_student_ids),
        status='Student',
    ).filter(
        pk__in=StudentExamSession.objects.filter(exam=selected_exam).values('student_id'),
    ).distinct().order_by('current_class__name', 'last_name', 'first_name') if selected_exam else Student.objects.none()

    session_map = {}
    question_list = []
    if selected_exam:
        session_map = {
            item.student_id: item
            for item in StudentExamSession.objects.filter(exam=selected_exam, student__in=student_queryset)
        }
        question_list = list(selected_exam.questions.all())

    for student in student_queryset:
        student_session = session_map.get(student.pk)
        student.attempt_session = student_session
        students.append(student)
        if student_session and student_session.is_completed:
            submissions[str(student.pk)] = [{
                'number': index + 1,
                'text': question.question_text,
                'options': {'A': question.option_a, 'B': question.option_b, 'C': question.option_c, 'D': question.option_d},
                'choice': student_session.responses.get(str(question.pk), ''),
                'correct': question.correct_answer,
            } for index, question in enumerate(question_list)]

    return render(request, 'portal/cbt_results.html', {
        'sessions': sessions,
        'terms': terms,
        'classrooms': classrooms,
        'subjects': subjects,
        'students': students,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'selected_term_obj': selected_term_obj,
        'selected_class': selected_class,
        'selected_subject': subject_query,
        'selected_exam': selected_exam,
        'subject_missing': not subject_query and bool(selected_session and selected_term and selected_class) and not selected_exam,
        'submissions_json': json.dumps(submissions),
        'filter_data': [
            ('session', 'Session', selected_session, sessions, 'pk'),
            ('term', 'Term', selected_term, terms, 'term'),
            ('classroom', 'Class', selected_class, classrooms, 'pk'),
            ('subject', 'Subject', subject_query, subjects, 'name'),
        ],
    })


@login_required(login_url='login')
def admin_results_view(request):
    if not is_admin_user(request.user) and not request.user.is_staff:
        return redirect('dashboard')
    return render(request, 'portal/admin_results.html', {'results': valid_subject_results(SubjectResult.objects.select_related('student', 'subject', 'term')).order_by('-term_id', 'student__last_name')})


@login_required(login_url='login')
@role_required(['Admin', 'Principal'])
@user_passes_test(is_admin_user, login_url='dashboard')
def results_process_view(request):
    context = _results_processing_context(request)
    selected_class = context['selected_class']
    selected_term_obj = context['selected_term_obj']
    status = None
    student_summaries = []
    if selected_class and selected_term_obj:
        status, _ = ClassResultStatus.objects.get_or_create(classroom=selected_class, term=selected_term_obj)
        students = students_in_term_classroom(selected_term_obj, selected_class)
        totals = {student.pk: Decimal('0') for student in students}
        for result in context['results'].filter(student__in=students):
            totals[result.student_id] = totals.get(result.student_id, Decimal('0')) + result.total
        student_summaries = sorted(
            ({'student': student, 'total_score': totals.get(student.pk, Decimal('0'))} for student in students),
            key=lambda row: row['total_score'], reverse=True,
        )
        previous_total = None
        position = 0
        for index, row in enumerate(student_summaries, start=1):
            if row['total_score'] != previous_total:
                position = index
                previous_total = row['total_score']
            row['position'] = position
            if selected_term_obj.term_name == 'Third Term':
                current_percentage = _student_term_percentage(row['student'], selected_term_obj)
                record = _third_term_record(row['student'], selected_term_obj, current_percentage)
                row.update({
                    'cumulative_average': record.cumulative_average,
                    'promotion_status': record.promotion_status,
                })
    context.update({'status': status, 'student_summaries': student_summaries, 'is_admin_viewer': is_admin_user(request.user)})
    return render(request, 'portal/results_process.html', context)


def _student_term_percentage(student, term):
    results = valid_subject_results(SubjectResult.objects.filter(
        student=student,
        term=term,
        term__session=term.session,
    ))
    summary = results.aggregate(total=Sum('total'))
    subject_count = results.count()
    return (summary['total'] or Decimal('0')) / subject_count if subject_count else Decimal('0.0')


def _third_term_record(student, term, current_percentage=None):
    if term.term_name != 'Third Term':
        return None
    term_one = AcademicTerm.objects.filter(session=term.session, term_name='First Term').first()
    term_two = AcademicTerm.objects.filter(session=term.session, term_name='Second Term').first()
    term_one_percentage = _student_term_percentage(student, term_one) if term_one else Decimal('0.0')
    term_two_percentage = _student_term_percentage(student, term_two) if term_two else Decimal('0.0')
    term_three_percentage = current_percentage if current_percentage is not None else _student_term_percentage(student, term)
    cumulative_average = ((term_one_percentage + term_two_percentage + term_three_percentage) / 3).quantize(Decimal('0.1'))
    record, created = StudentTermRecord.objects.get_or_create(
        student=student,
        term=term,
        defaults={
            'term_one_percentage': term_one_percentage,
            'term_two_percentage': term_two_percentage,
            'term_three_percentage': term_three_percentage,
            'cumulative_average': cumulative_average,
            'promotion_status': 'Promoted' if cumulative_average >= Decimal('45.0') else 'Repeated',
        },
    )
    if not created:
        record.term_one_percentage = term_one_percentage
        record.term_two_percentage = term_two_percentage
        record.term_three_percentage = term_three_percentage
        record.cumulative_average = cumulative_average
        record.save(update_fields=['term_one_percentage', 'term_two_percentage', 'term_three_percentage', 'cumulative_average'])
    return record


@login_required(login_url='login')
def update_promotion_status_view(request):
    if not is_admin_user(request.user) or request.method != 'POST':
        return redirect('dashboard')
    term = get_object_or_404(AcademicTerm, pk=request.POST.get('term_id'))
    student = get_object_or_404(Student, pk=request.POST.get('student_id'))
    promotion_status = request.POST.get('promotion_status') or request.POST.get(f'promotion_status_{student.pk}')
    if term.term_name == 'Third Term' and promotion_status in {'Promoted', 'Repeated'}:
        record = _third_term_record(student, term)
        record.promotion_status = promotion_status
        record.save(update_fields=['promotion_status'])
        messages.success(request, 'Promotion status updated.')
    return redirect(f"{reverse('results_process')}?classroom={request.POST.get('classroom_id', '')}&session={term.session_id}&term={term.pk}")


@login_required(login_url='login')
def session_rollover_view(request):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    if request.method == 'POST' and principal_action_denied(request):
        return redirect('session_rollover')
    active_session = AcademicSession.objects.filter(is_active=True).first()
    session_id = request.POST.get('session_id') or request.GET.get('session_id')
    closing_session = get_object_or_404(AcademicSession, pk=session_id) if session_id else active_session
    if request.method == 'POST' and request.POST.get('action') == 'execute_rollover':
        if not closing_session:
            messages.error(request, 'Select a closing session before executing the rollover.')
            return redirect('session_rollover')
        redirect_url = f"{reverse('session_rollover')}?session_id={closing_session.pk}"
        moved = 0
        graduated = 0
        unmapped = 0
        with transaction.atomic():
            closing_session = AcademicSession.objects.select_for_update().get(pk=closing_session.pk)
            if closing_session.rollover_completed:
                messages.info(request, 'Session rollover has already been completed for this session.')
                return redirect(redirect_url)
            if not StudentTermRecord.objects.filter(
                term__session=closing_session,
                term__term_name='Third Term',
            ).exists():
                messages.error(request, 'Session rollover is only available at the end of the Third Term.')
                return redirect(redirect_url)
            next_session = AcademicSession.objects.filter(name__gt=closing_session.name).order_by('name').first()
            first_term = AcademicTerm.objects.filter(session=next_session, term_name='First Term').first() if next_session else None
            if not first_term:
                messages.error(request, 'Create the First Term for the next academic session before executing rollover.')
                return redirect(redirect_url)
            records = StudentTermRecord.objects.select_for_update().select_related(
                'student__current_class', 'term', 'student__current_class__next_class',
            ).filter(term__session=closing_session, term__term_name='Third Term', student__status__in=['Active', 'Student'])
            for record in records:
                student = record.student
                if record.promotion_status != 'Promoted':
                    continue
                current_class = student.current_class
                rollover_record, _ = SessionRolloverRecord.objects.get_or_create(
                    closing_session=closing_session,
                    student=student,
                    defaults={
                        'original_class': current_class,
                        'original_status': student.status,
                        'target_term': first_term,
                    },
                )
                if current_class and current_class.is_terminal:
                    student.status = 'Graduated'
                    student.save(update_fields=['status'])
                    graduated += 1
                    continue
                next_class = current_class.next_class if record.promotion_status == 'Promoted' and current_class else current_class
                if not next_class:
                    unmapped += 1
                    continue
                if record.promotion_status == 'Promoted' and student.current_class_id != next_class.pk:
                    student.current_class = next_class
                    student.save(update_fields=['current_class'])
                    moved += 1
                existing_enrollment = TermEnrollment.objects.select_for_update().filter(
                    student=student,
                    term=first_term,
                ).first()
                enrollment, created = TermEnrollment.objects.select_for_update().update_or_create(
                    student=student,
                    term=first_term,
                    defaults={'classroom': student.current_class},
                )
                if existing_enrollment:
                    rollover_record.previous_enrollment_class = existing_enrollment.classroom
                    rollover_record.save(update_fields=['previous_enrollment_class'])
                elif created:
                    rollover_record.created_enrollment = True
                    rollover_record.save(update_fields=['created_enrollment'])
            closing_session.rollover_completed = True
            closing_session.save(update_fields=['rollover_completed'])
        messages.success(request, 'Session rollover executed successfully. Students have been migrated.')
        if unmapped:
            messages.warning(request, f'{unmapped} promoted student(s) were skipped because their class has no next-class mapping.')
        return redirect(redirect_url)

    if request.method == 'POST' and request.POST.get('action') == 'revert_rollover':
        if not closing_session:
            messages.error(request, 'Select a closing session before reverting the rollover.')
            return redirect('session_rollover')
        redirect_url = f"{reverse('session_rollover')}?session_id={closing_session.pk}"
        with transaction.atomic():
            closing_session = AcademicSession.objects.select_for_update().get(pk=closing_session.pk)
            if not closing_session.rollover_completed:
                messages.error(request, 'This session has not been rolled over.')
                return redirect(redirect_url)
            rollover_records = SessionRolloverRecord.objects.select_for_update().filter(
                closing_session=closing_session,
            ).select_related('student', 'original_class', 'target_term')
            for rollover_record in rollover_records:
                student = rollover_record.student
                student.current_class = rollover_record.original_class
                student.status = rollover_record.original_status
                student.save(update_fields=['current_class', 'status'])
                if rollover_record.created_enrollment:
                    TermEnrollment.objects.filter(
                        student=student,
                        term=rollover_record.target_term,
                    ).delete()
                elif rollover_record.previous_enrollment_class:
                    TermEnrollment.objects.filter(
                        student=student,
                        term=rollover_record.target_term,
                    ).update(classroom=rollover_record.previous_enrollment_class)
            rollover_records.delete()
            closing_session.rollover_completed = False
            closing_session.save(update_fields=['rollover_completed'])
        messages.success(request, 'Rollover successfully reverted for testing.')
        return redirect(redirect_url)

    records = StudentTermRecord.objects.filter(
        term__session=closing_session,
        term__term_name='Third Term',
        student__status__in=['Active', 'Student'],
    ).select_related('student__current_class', 'student__current_class__next_class') if closing_session else StudentTermRecord.objects.none()
    promoted_records = list(records.filter(promotion_status='Promoted'))
    terminal_records = [record for record in promoted_records if record.student.current_class and record.student.current_class.is_terminal]
    standard_promotion_records = [
        record for record in promoted_records
        if record.student.current_class
        and not record.student.current_class.is_terminal
    ]
    unmapped_count = sum(
        1 for record in promoted_records
        if not record.student.current_class
        or (not record.student.current_class.is_terminal and not record.student.current_class.next_class)
    )
    all_configured = all(c.next_class is not None or c.is_terminal for c in ClassRoom.objects.all())
    has_third_term_records = StudentTermRecord.objects.filter(
        term__session=closing_session,
        term__term_name='Third Term',
    ).exists() if closing_session else False
    context = {
        'sessions': AcademicSession.objects.order_by('-name'),
        'active_session': active_session,
        'closing_session': closing_session,
        'record_count': records.count(),
        'promoted_count': len(standard_promotion_records),
        'graduating_count': len(terminal_records),
        'repeated_count': records.filter(promotion_status='Repeated').count(),
        'unmapped_count': unmapped_count,
        'all_configured': all_configured,
        'is_ready': all_configured,
        'has_third_term_records': has_third_term_records,
        'is_rolled_over': closing_session.rollover_completed if closing_session else False,
        'classrooms': ClassRoom.objects.select_related('next_class').order_by('section', 'level_number', 'name'),
    }
    return render(request, 'portal/session_rollover.html', context)


@login_required(login_url='login')
def graduated_alumni_view(request):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    graduated_students = Student.objects.filter(status='Graduated').select_related('current_class').prefetch_related(
        'term_records__term__session',
    ).order_by('last_name', 'first_name')
    sessions = AcademicSession.objects.order_by('-name')
    classrooms = ClassRoom.objects.order_by('section', 'sequence', 'name')
    session_id = request.GET.get('session')
    classroom_id = request.GET.get('classroom')
    selected_session = sessions.filter(pk=session_id).first() if session_id else None
    if session_id:
        graduated_students = graduated_students.filter(term_records__term__session_id=session_id)
    if classroom_id:
        graduated_students = graduated_students.filter(current_class_id=classroom_id)
    graduated_students = list(graduated_students)
    for student in graduated_students:
        student.final_term_record = next(
            (
                record for record in reversed(list(student.term_records.all()))
                if record.term.term_name == 'Third Term'
                and (not selected_session or record.term.session_id == selected_session.pk)
            ),
            None,
        )
    return render(request, 'portal/graduated_alumni.html', {
        'graduated_students': graduated_students,
        'sessions': sessions,
        'classrooms': classrooms,
        'selected_session': session_id,
        'selected_classroom': classroom_id,
    })


@login_required(login_url='login')
def manage_fee_structures(request):
    if not is_finance_user(request.user):
        return redirect('dashboard')
    if request.method == 'POST':
        action = request.POST.get('action')
        if action in {'edit_fee_structure', 'delete_fee_structure'}:
            structure = get_object_or_404(FeeStructure, pk=request.POST.get('fee_structure_id'))
            if action == 'delete_fee_structure':
                if principal_action_denied(request):
                    return redirect('manage_fee_structures')
                structure.delete()
                messages.success(request, 'Fee structure deleted successfully.')
            else:
                try:
                    amount_required = Decimal(request.POST.get('amount_required', '0'))
                    if amount_required < 0:
                        raise ValueError
                except (InvalidOperation, TypeError, ValueError):
                    messages.error(request, 'Enter a valid non-negative fee amount.')
                else:
                    structure.amount_required = amount_required
                    structure.save()
                    messages.success(request, 'Fee structure amount updated successfully.')
            return redirect('manage_fee_structures')
        try:
            classroom_id = request.POST.get('classroom')
            term_id = request.POST.get('term')
            session_id = request.POST.get('session')
            amount_required = Decimal(request.POST.get('amount_required', '0'))
            if amount_required < 0:
                raise ValueError
            classroom = get_object_or_404(ClassRoom, pk=classroom_id)
            session = get_object_or_404(AcademicSession, pk=session_id)
            term = get_object_or_404(AcademicTerm, pk=term_id, session=session)
            FeeStructure.objects.update_or_create(
                classroom=classroom,
                term=term,
                session=session,
                defaults={'amount_required': amount_required},
            )
            messages.success(request, 'Fee structure saved successfully.')
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, 'Enter a valid non-negative fee amount.')
        return redirect('manage_fee_structures')
    active_session = AcademicSession.objects.filter(is_active=True).first()
    active_term = AcademicTerm.objects.filter(is_active=True).first()
    return render(request, 'portal/fee_structures.html', {
        'fee_structures': FeeStructure.objects.select_related('classroom', 'term', 'session').order_by('-term__start_date', 'classroom__name'),
        'sessions': AcademicSession.objects.order_by('-name'),
        'active_session': active_session,
        'active_term': active_term,
        'classrooms': ClassRoom.objects.order_by('section', 'sequence', 'name'),
        'terms': AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name'),
    })


@login_required(login_url='login')
@bursar_required
def bursary_dashboard(request):
    if not is_finance_user(request.user):
        return redirect('dashboard')
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    if request.method == 'POST':
        account = get_object_or_404(StudentFeeAccount, pk=request.POST.get('account_id'))
        if request.POST.get('action') == 'record_payment':
            try:
                payment = Decimal(request.POST.get('amount_paid', '0'))
                if payment <= 0:
                    raise ValueError
            except (InvalidOperation, TypeError, ValueError):
                messages.error(request, 'Enter a valid non-negative payment amount.')
            else:
                try:
                    with transaction.atomic():
                        apply_fifo_payment(account, payment, request.user)
                except ValueError as error:
                    messages.error(request, str(error))
                else:
                    log_security_action(request, 'PAYMENT_RECORDED', f'{account.student} - {account.term}', {
                        'before': {'amount_paid': str(account.amount_paid)},
                        'after': {'payment_received': str(payment)},
                    })
                    messages.success(request, 'Payment allocated to the oldest outstanding term balances first.')
        elif request.POST.get('action') == 'toggle_clearance':
            if principal_action_denied(request):
                return redirect('bursary_dashboard')
            previous_clearance = account.is_cleared
            if request.POST.get('is_cleared') == '1':
                accounts = fee_accounts_through(account)
                if any(candidate.balance > 0 for candidate in accounts):
                    messages.error(request, 'Clear all previous and current term balances before marking this account cleared.')
                else:
                    account.is_cleared = True
                    account.save(update_fields=['is_cleared'])
                    log_security_action(request, 'DEBT_OVERRIDDEN', f'{account.student} - {account.term}', {
                        'before': {'is_cleared': previous_clearance},
                        'after': {'is_cleared': True},
                    })
                    messages.success(request, 'Fee clearance status updated.')
            else:
                account.is_cleared = False
                account.save(update_fields=['is_cleared'])
                log_security_action(request, 'DEBT_OVERRIDDEN', f'{account.student} - {account.term}', {
                    'before': {'is_cleared': previous_clearance},
                    'after': {'is_cleared': False},
                })
                messages.success(request, 'Fee clearance status updated.')
        return redirect('bursary_dashboard')
    sessions = AcademicSession.objects.order_by('-name')
    all_terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'start_date', 'pk')
    active_session = active_term.session if active_term else sessions.filter(is_active=True).first()
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else active_session
    selected_session = selected_session or active_session
    terms = all_terms.filter(session=selected_session) if selected_session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else terms.filter(pk=active_term.pk).first() if active_term else None
    selected_term = selected_term or terms.first()
    classroom_id = request.GET.get('classroom')
    selected_class = ClassRoom.objects.filter(pk=classroom_id).first() if classroom_id else None
    if selected_term and selected_class:
        students = students_in_term_classroom(selected_term, selected_class)
        if not TermEnrollment.objects.filter(term=selected_term).exists():
            students = Student.objects.filter(
                Q(current_class=selected_class) | Q(subject_results__term=selected_term),
            ).distinct()
        fee_structure = FeeStructure.objects.filter(
            classroom=selected_class,
            term=selected_term,
            session=selected_session,
        ).first()
        with transaction.atomic():
            for student in students:
                account, created = StudentFeeAccount.objects.get_or_create(
                    student=student,
                    term=selected_term,
                    session=selected_session,
                    defaults={'total_billed': fee_structure.amount_required if fee_structure else Decimal('0')},
                )
                if created and account.balance > 0 and student.parent and student.parent.user:
                    _notify_users(
                        [student.parent.user],
                        'School fees due',
                        f'School fees for {student.first_name} {student.last_name} are now due. Please review the outstanding balance.',
                        reverse('parent_bursary'),
                    )
    accounts = StudentFeeAccount.objects.select_related('student', 'student__current_class', 'term', 'session').prefetch_related('payments')
    if selected_term:
        accounts = accounts.filter(term=selected_term, session=selected_session)
        if selected_class:
            accounts = accounts.filter(student__in=students)
    else:
        accounts = accounts.none()
    accounts = list(accounts.order_by('student__last_name', 'student__first_name'))
    for account in accounts:
        account.rollover_balance = student_outstanding_balance(account.student, selected_term) - max(account.balance, Decimal('0'))
        account.has_rollover_debt = account.rollover_balance > 0
    return render(request, 'portal/bursary.html', {
        'active_term': active_term,
        'sessions': sessions,
        'terms': terms,
        'selected_session': selected_session.pk if selected_session else '',
        'selected_session_obj': selected_session,
        'selected_term': selected_term.pk if selected_term else '',
        'selected_term_obj': selected_term,
        'terms_json': json.dumps(session_terms_map()),
        'accounts': accounts,
        'classrooms': ClassRoom.objects.order_by('section', 'sequence', 'name'),
        'selected_classroom': classroom_id,
        'selected_class': selected_class,
    })


@login_required(login_url='login')
@bursar_required
def bursar_dashboard_view(request):
    return render(request, 'portal/bursar_home.html')


@login_required(login_url='login')
@bursar_required
def export_fee_ledger_view(request):
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    accounts = StudentFeeAccount.objects.select_related('student', 'term', 'session').filter(term=active_term) if active_term else StudentFeeAccount.objects.none()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="fee_ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(['Student ID', 'Student Name', 'Session', 'Term', 'Total Billed', 'Amount Paid', 'Balance', 'Cleared'])
    for account in accounts.order_by('student__last_name', 'student__first_name'):
        writer.writerow([
            account.student.student_id,
            f'{account.student.last_name} {account.student.first_name}',
            account.session.name,
            account.term.term_name,
            account.total_billed,
            account.amount_paid,
            account.balance,
            'Yes' if account.is_cleared else 'No',
        ])
    return response


@login_required(login_url='login')
@bursar_required
def payment_history_view(request):
    payments = FeePayment.objects.select_related(
        'account__student', 'account__session', 'account__term', 'recorded_by',
    ).order_by('-paid_at', '-pk')
    sessions = AcademicSession.objects.order_by('-name')
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else None
    terms = AcademicTerm.objects.filter(session=selected_session).order_by('start_date', 'pk') if selected_session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else None
    if selected_session:
        payments = payments.filter(account__session=selected_session)
    if selected_term:
        payments = payments.filter(account__term=selected_term)
    return render(request, 'portal/payment_history.html', {
        'payments': payments,
        'sessions': sessions,
        'terms': terms,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'terms_json': json.dumps(session_terms_map()),
    })


@login_required(login_url='login')
@bursar_required
def defaulters_list_view(request):
    accounts = StudentFeeAccount.objects.select_related(
        'student__current_class', 'session', 'term',
    ).filter(amount_paid__lt=F('total_billed')).order_by(
        'student__last_name', 'student__first_name', 'term__start_date',
    )
    sessions = AcademicSession.objects.order_by('-name')
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else None
    terms = AcademicTerm.objects.filter(session=selected_session).order_by('start_date', 'pk') if selected_session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else None
    if selected_session:
        accounts = accounts.filter(session=selected_session)
    if selected_term:
        accounts = accounts.filter(term=selected_term)
    return render(request, 'portal/defaulters_list.html', {
        'accounts': accounts,
        'sessions': sessions,
        'terms': terms,
        'selected_session': selected_session,
        'selected_term': selected_term,
        'terms_json': json.dumps(session_terms_map()),
    })


CLASSROOM_ASSUMED_CAPACITY = 40


@login_required(login_url='login')
@registrar_required
def registrar_dashboard_view(request):
    return render(request, 'portal/registrar_home.html')


@login_required(login_url='login')
@registrar_required
def document_hub_view(request):
    query = request.GET.get('q', '').strip()
    applicants = Applicant.objects.select_related('campaign', 'intended_class', 'enrolled_student')
    students = Student.objects.select_related('current_class', 'applicant_record')
    if query:
        applicants = applicants.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(temp_reg_number__icontains=query)
            | Q(parent_name__icontains=query)
        )
        students = students.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(student_id__icontains=query)
            | Q(lin__icontains=query)
        )
    applicants = applicants.order_by('-submitted_at')[:100]
    students = students.order_by('last_name', 'first_name')[:100]
    return render(request, 'portal/document_hub.html', {
        'applicants': applicants,
        'students': students,
        'query': query,
        'applicant_count': applicants.count() if hasattr(applicants, 'count') else len(applicants),
        'student_count': students.count() if hasattr(students, 'count') else len(students),
    })


@login_required(login_url='login')
@principal_required
def principal_dashboard_view(request):
    today = timezone.localdate()
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    pending_approvals = 0 if not active_term or active_term.broadsheet_approved else ClassRoom.objects.count()
    average_result = valid_subject_results(SubjectResult.objects.filter(term=active_term)).aggregate(avg=Avg('total'))['avg'] if active_term else None
    active_students = Student.objects.filter(status='Student')
    total_students = active_students.count()
    present_today = Attendance.objects.filter(date=today, status='Present', student__status='Student').values('student').distinct().count()
    daily_attendance_rate = round((present_today / total_students) * 100) if total_students else 0
    active_staff = Teacher.objects.filter(status='Active').count()
    staff_emails = list(Teacher.objects.filter(status='Active').exclude(email='').values_list('email', flat=True))
    return render(request, 'portal/principal_dashboard.html', {
        'active_term': active_term,
        'pending_approvals': pending_approvals,
        'average_result': average_result,
        'daily_attendance_rate': daily_attendance_rate,
        'present_today': present_today,
        'total_students': total_students,
        'active_staff': active_staff,
        'staff_emails': staff_emails,
    })


@login_required(login_url='login')
@principal_required
def school_wide_analytics_view(request):
    today = timezone.localdate()
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    active_students = Student.objects.filter(status='Student')
    classroom_breakdown = []
    for classroom in ClassRoom.objects.order_by('section', 'level_number', 'name'):
        total = active_students.filter(current_class=classroom).count()
        present = Attendance.objects.filter(date=today, status='Present', classroom=classroom, student__status='Student').values('student').distinct().count()
        average = valid_subject_results(SubjectResult.objects.filter(term=active_term, student__current_class=classroom)).aggregate(avg=Avg('total'))['avg'] if active_term else None
        classroom_breakdown.append({
            'classroom': classroom,
            'total': total,
            'attendance_rate': round((present / total) * 100) if total else 0,
            'average_result': round(average) if average is not None else None,
        })
    return render(request, 'portal/school_wide_analytics.html', {
        'active_term': active_term,
        'classroom_breakdown': classroom_breakdown,
    })


@login_required(login_url='login')
def publish_results_view(request):
    if not is_admin_user(request.user) or request.method != 'POST':
        return redirect('dashboard')
    classroom = get_object_or_404(ClassRoom, pk=request.POST.get('class_id'))
    term = get_object_or_404(AcademicTerm, pk=request.POST.get('term_id'))
    if not term.broadsheet_approved:
        messages.error(request, 'Broadsheet must be approved before publishing.')
        return redirect(f"{reverse('results_process')}?classroom={classroom.pk}&session={term.session_id}&term={term.pk}")
    status, _ = ClassResultStatus.objects.get_or_create(classroom=classroom, term=term)
    previous_status = status.is_published
    status.is_published = True
    status.scheduled_publish_date = None
    status.save(update_fields=['is_published', 'scheduled_publish_date'])
    if not previous_status:
        _notify_users(
            _parent_recipient_users(classroom),
            f'Results published for {classroom.name}',
            f'The {term.term_name} results for {classroom.name} are now available in the parent portal.',
            reverse('parent_report_cards'),
        )
    log_security_action(request, 'RESULT_PUBLISHED', f'{classroom.name} - {term.term_name} {term.session.name}', {
        'before': {'is_published': previous_status}, 'after': {'is_published': True},
    })
    messages.success(request, 'Results published to parents.')
    return redirect(f"{reverse('results_process')}?classroom={classroom.pk}&session={term.session_id}&term={term.pk}")


@login_required(login_url='login')
def unpublish_results_view(request):
    if not is_admin_user(request.user) or request.method != 'POST':
        return redirect('dashboard')
    classroom = get_object_or_404(ClassRoom, pk=request.POST.get('class_id'))
    term = get_object_or_404(AcademicTerm, pk=request.POST.get('term_id'))
    status, _ = ClassResultStatus.objects.get_or_create(classroom=classroom, term=term)
    previous_status = status.is_published
    status.is_published = False
    status.scheduled_publish_date = None
    status.save(update_fields=['is_published', 'scheduled_publish_date'])
    log_security_action(request, 'RESULT_UNPUBLISHED', f'{classroom.name} - {term.term_name} {term.session.name}', {
        'before': {'is_published': previous_status}, 'after': {'is_published': False},
    })
    messages.success(request, 'Results unpublished.')
    return redirect(f"{reverse('results_process')}?classroom={classroom.pk}&session={term.session_id}&term={term.pk}")


@login_required(login_url='login')
def schedule_results_view(request):
    if not is_admin_user(request.user) or request.method != 'POST':
        return redirect('dashboard')
    classroom = get_object_or_404(ClassRoom, pk=request.POST.get('class_id'))
    term = get_object_or_404(AcademicTerm, pk=request.POST.get('term_id'))
    scheduled_at = parse_datetime(request.POST.get('scheduled_publish_date', ''))
    if not scheduled_at:
        messages.error(request, 'Please provide a valid schedule date and time.')
    else:
        if timezone.is_naive(scheduled_at):
            scheduled_at = timezone.make_aware(scheduled_at)
        status, _ = ClassResultStatus.objects.get_or_create(classroom=classroom, term=term)
        status.is_published = False
        status.scheduled_publish_date = scheduled_at
        status.save(update_fields=['is_published', 'scheduled_publish_date'])
        messages.success(request, 'Result release scheduled successfully.')
    return redirect(f"{reverse('results_process')}?classroom={classroom.pk}&session={term.session_id}&term={term.pk}")


@login_required(login_url='login')
def update_next_term_view(request):
    if not is_admin_user(request.user) or request.method != 'POST':
        return redirect('dashboard')
    term = get_object_or_404(AcademicTerm, pk=request.POST.get('term_id'))
    next_term_begins = parse_date(request.POST.get('next_term_date') or request.POST.get('next_term_begins', ''))
    if not next_term_begins:
        messages.error(request, 'Please provide a valid next term start date.')
    else:
        term.next_term_begins = next_term_begins
        term.save(update_fields=['next_term_begins'])
        messages.success(request, 'Next term start date saved.')
    classroom_id = request.POST.get('classroom_id', '')
    return redirect(f"{reverse('results_process')}?classroom={classroom_id}&session={term.session_id}&term={term.pk}")


@login_required(login_url='login')
def preview_report_card_view(request, student_id, session_id, term_id):
    if not is_admin_user(request.user) and not getattr(request.user, 'teacher_record', None):
        return redirect('dashboard')
    student = get_object_or_404(Student, pk=student_id)
    term = get_object_or_404(AcademicTerm, pk=term_id, session_id=session_id)
    fee_account = StudentFeeAccount.objects.filter(student=student, term=term, session=term.session).first()
    if fee_account and not fee_account.is_cleared and not is_admin_user(request.user):
        return render(request, 'portal/report_locked.html', {'student': student, 'fee_account': fee_account, 'parent_lock': True})
    context = _report_card_context(student, term, published=True)
    context['fee_override'] = bool(fee_account and not fee_account.is_cleared and is_admin_user(request.user))
    context['fee_balance'] = fee_account.balance if fee_account else None
    return render(request, 'portal/report_card.html', context)


def _subject_grade(total):
    total = float(total)
    if total >= 70:
        return 'A', 'Excellent'
    if total >= 60:
        return 'B', 'Very Good'
    if total >= 50:
        return 'C', 'Good'
    if total >= 45:
        return 'D', 'Fair'
    if total >= 40:
        return 'E', 'Pass'
    return 'F', 'Fail'


def _report_card_context(student, term, published):
    session = term.session
    classroom = historical_classroom(student, term)
    results = list(valid_subject_results(SubjectResult.objects.filter(
        student=student,
        term=term,
        term__session=term.session,
    ).select_related('subject')).order_by('subject__name')) if published else []
    previous_term = AcademicTerm.objects.filter(start_date__lt=term.start_date).order_by('-start_date').first() if term.start_date else None
    subject_rows = []
    total_score = Decimal('0')
    for result in results:
        past_result = SubjectResult.objects.filter(student=student, term=previous_term, subject=result.subject).first() if previous_term else None
        past_total = past_result.total if past_result else None
        cumulative = ((result.total + past_total) / 2) if past_total is not None else result.total
        grade, remark = _subject_grade(result.total)
        subject_rows.append({'result': result, 'past_total': past_total, 'cumulative': cumulative, 'grade': grade, 'remark': remark})
        total_score += result.total
    subject_count = len(results)
    percentage = (total_score / (subject_count * 100) * 100).quantize(Decimal('0.1')) if subject_count else Decimal('0.0')
    is_third_term = term.term_name == 'Third Term'
    third_term_record = _third_term_record(student, term, percentage) if is_third_term else None
    next_classroom = None
    if is_third_term and classroom and classroom.level_number is not None:
        next_classroom = ClassRoom.objects.filter(
            section=classroom.section,
            level_number__gt=classroom.level_number,
        ).order_by('level_number').first()
    position = None
    if classroom:
        classmate_totals = []
        for classmate in students_in_term_classroom(term, classroom):
            classmate_total = valid_subject_results(SubjectResult.objects.filter(
                student=classmate,
                term=term,
                term__session=term.session,
            )).aggregate(total=Sum('total'))['total'] or Decimal('0')
            classmate_totals.append((classmate.pk, classmate_total))
        classmate_totals.sort(key=lambda row: row[1], reverse=True)
        previous_total = None
        rank = 0
        for index, (student_pk, classmate_total) in enumerate(classmate_totals, start=1):
            if classmate_total != previous_total:
                rank = index
                previous_total = classmate_total
            if student_pk == student.pk:
                position = rank
                break
    week_dates = AcademicWeek.objects.filter(term=term).aggregate(
        term_start=Min('start_date'),
        term_end=Max('end_date'),
    )
    term_start = week_dates['term_start']
    term_end = week_dates['term_end']
    days_opened = 0
    days_present = 0
    days_absent = 0
    if term_start and term_end:
        holidays = set(Holiday.objects.filter(term=term).values_list('date', flat=True))
        current_date = term_start
        while current_date <= term_end:
            if current_date.weekday() < 5 and current_date not in holidays:
                days_opened += 1
            current_date += datetime.timedelta(days=1)
        days_present = Attendance.objects.filter(student=student, session=session, status__in=('Present', 'Late'), date__range=(term_start, term_end)).count()
        days_absent = days_opened - days_present
    evaluation = StudentEvaluation.objects.filter(student=student, session=session, term=term).first()
    character_traits = [('attentiveness', 'Attentiveness'), ('punctuality', 'Punctuality'), ('self_control', 'Self Control'), ('relationship_with_others', 'Relationship With Others')]
    skill_traits = [('music', 'Music'), ('indoor_games', 'Indoor Games'), ('outdoor_games', 'Outdoor Games'), ('club_association', 'Club/Association')]
    ratings = [getattr(evaluation, field, None) for field, _ in character_traits + skill_traits] if evaluation else []
    ratings = [value for value in ratings if value is not None]
    average_rating = (sum(ratings) / len(ratings)) if ratings else None
    automated_comment = ''
    comment_bank_entry = AutomatedCommentBank.objects.filter(min_score__lte=percentage, max_score__gte=percentage).first()
    if comment_bank_entry:
        if average_rating is None or average_rating <= 2:
            automated_comment = comment_bank_entry.char_poor
        elif average_rating <= 4:
            automated_comment = comment_bank_entry.char_good
        else:
            automated_comment = comment_bank_entry.char_excellent
    result_status = ClassResultStatus.objects.filter(classroom=classroom, term=term).first() if classroom else None
    publish_date = None
    if result_status:
        publish_date = result_status.scheduled_publish_date or (timezone.now() if result_status.is_published else None)
    return {
        'student': student,
        'term': term,
        'session': session,
        'classroom': classroom,
        'results': results,
        'subject_rows': subject_rows,
        'total_score': total_score,
        'percentage': percentage,
        'position': position,
        'term_start': term_start,
        'term_end': term_end,
        'days_opened': days_opened,
        'days_school_opened': days_opened,
        'days_present': days_present,
        'days_absent': days_absent,
        'evaluation': evaluation,
        'character_traits': character_traits,
        'skill_traits': skill_traits,
        'teacher_comment': student.teacher_comment,
        'automated_proprietress_comment': automated_comment,
        'publish_date': publish_date,
        'next_term_begins': term.next_term_begins,
        'is_third_term': is_third_term,
        'term_one_percentage': third_term_record.term_one_percentage if third_term_record else None,
        'term_two_percentage': third_term_record.term_two_percentage if third_term_record else None,
        'term_three_percentage': third_term_record.term_three_percentage if third_term_record else None,
        'cumulative_average': third_term_record.cumulative_average if third_term_record else None,
        'promotion_status': third_term_record.promotion_status if third_term_record else None,
        'next_classroom': next_classroom,
        'published': published,
    }


def _results_processing_context(request):
    results = valid_subject_results(SubjectResult.objects.select_related('student', 'subject', 'term', 'term__session'))
    teacher = getattr(request.user, 'teacher_record', None)
    classrooms = classroom_progression_order(ClassRoom.objects.all()) if is_admin_user(request.user) else classroom_progression_order(teacher.assigned_class.all())
    if teacher and not is_admin_user(request.user):
        results = results.filter(student__term_enrollments__classroom__in=classrooms)
    sessions = AcademicSession.objects.order_by('-name')
    terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name')
    active_session = AcademicSession.objects.filter(is_active=True).first()
    active_term = AcademicTerm.objects.filter(is_active=True).first()
    session_id = request.GET.get('session') or (active_session.pk if active_session else None)
    term_id = request.GET.get('term') or (active_term.pk if active_term else None)
    classroom_id = request.GET.get('classroom') or request.GET.get('class')
    if session_id:
        results = results.filter(term__session_id=session_id)
        terms = terms.filter(session_id=session_id)
    if term_id:
        results = results.filter(term_id=term_id)
    selected_class = classrooms.filter(pk=classroom_id).first() if classroom_id else None
    selected_session_obj = sessions.filter(pk=session_id).first() if session_id else None
    selected_term_obj = terms.filter(pk=term_id).first() if term_id else None
    if selected_class and selected_term_obj:
        results = results.filter(
            student__term_enrollments__term=selected_term_obj,
            student__term_enrollments__classroom=selected_class,
        )
    return {
        'results': results.order_by('-term_id', 'student__last_name'),
        'classrooms': classrooms,
        'sessions': sessions,
        'terms': terms,
        'selected_classroom': classroom_id,
        'selected_session': session_id,
        'selected_term': term_id,
        'selected_class': selected_class,
        'selected_session_obj': selected_session_obj,
        'selected_term_obj': selected_term_obj,
        'terms_json': json.dumps(session_terms_map()),
    }


@login_required(login_url='login')
@login_required(login_url='login')
def results_uploads_view(request):
    teacher = getattr(request.user, 'teacher_record', None)
    if not is_admin_user(request.user) and not teacher:
        return redirect('dashboard')
    context = _result_upload_context(request)
    selected_class = context['selected_class']
    selected_term = context['selected_term']
    subjects = valid_subjects(
        Subject.objects.filter(classroomsubject__class_room=selected_class).distinct()
    ).order_by('name') if selected_class else Subject.objects.none()
    is_split_class = is_cbt_eligible_class(selected_class)
    if request.method == 'POST':
        if results_are_locked(selected_class, selected_term):
            messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
            return redirect(request.get_full_path())
        scores = {}
        for student in context['students']:
            for subject in subjects:
                try:
                    scores[(student.pk, subject.pk)] = (
                        max(0, min(30, float(request.POST.get(f'ca_{student.pk}_{subject.pk}', 0) or 0))),
                        max(0, min(40, float(request.POST.get(f'theory_{student.pk}_{subject.pk}', 0) or 0))),
                    )
                except (TypeError, ValueError):
                    messages.error(request, 'Scores must be valid numbers within the allowed ranges.')
                    return redirect(request.get_full_path())
        with transaction.atomic():
            for student in context['students']:
                for subject in subjects:
                    result, _ = SubjectResult.objects.get_or_create(
                        student=student, term=selected_term, subject=subject,
                    )
                    result.continuous_assessment, result.theory = scores[(student.pk, subject.pk)]
                    attempt = CBTAttempt.objects.filter(
                        exam__subject=subject,
                        exam__classroom=selected_class,
                        exam__term=selected_term,
                        student=student,
                        status='submitted',
                    ).order_by('-submitted_at').first()
                    question_count = attempt.exam.questions.count() if attempt else 0
                    result.cbt_obj = Decimal(attempt.score * 30 / question_count) if attempt and question_count else Decimal('0')
                    result.save()
        log_security_action(request, 'SCORE_MODIFIED', f'{selected_class.name} - {selected_term.term_name} {selected_term.session.name}', {
            'before': {},
            'after': {'students_updated': context['students'].count(), 'subjects_updated': subjects.count()},
        })
        messages.success(request, 'CA and exam scores saved successfully.')
        return redirect(request.get_full_path())
    results = {}
    for result in SubjectResult.objects.filter(
        student__in=context['students'],
        term=selected_term,
        term__session_id=selected_term.session_id if selected_term else None,
        subject__in=subjects,
    ):
        results.setdefault(result.student_id, {})[result.subject_id] = result
    for student in context['students']:
        student_results = results.setdefault(student.pk, {})
        for subject in subjects:
            student_results.setdefault(
                subject.pk,
                SubjectResult(student=student, term=selected_term, subject=subject),
            )
    cbt_scores = {}
    if is_split_class:
        for subject in subjects:
            subject.max_theory = 20 if subject.name.lower() in ('mathematics', 'english') else 30
        for student in context['students']:
            for subject in subjects:
                attempt = CBTAttempt.objects.filter(
                    exam__subject=subject,
                    exam__classroom=selected_class,
                    exam__term=selected_term,
                    student=student,
                    status='submitted',
                ).order_by('-submitted_at').first()
                cbt_scores.setdefault(student.pk, {})[subject.pk] = (attempt.score * 2) if attempt else 0
    context.update({
        'subjects': subjects,
        'results': results,
        'is_split_class': is_split_class,
        'cbt_scores': cbt_scores,
    })
    return render(request, 'portal/results_uploads.html', context)


def _grade_cbt_session(session, exam):
    total_questions = exam.questions.count()
    correct_answers = 0
    for question in exam.questions.all():
        if session.responses.get(str(question.pk), '') == question.correct_answer:
            correct_answers += 1
    session.score = float(correct_answers)
    session.is_completed = True
    session.submitted_at = timezone.now()
    session.save(update_fields=['responses', 'score', 'is_completed', 'submitted_at'])
    return total_questions, correct_answers


@login_required(login_url='login')
def cbt_instructions_view(request, pk):
    student = getattr(request.user, 'student_record', None)
    exam = get_object_or_404(CBTExam.objects.select_related('subject', 'classroom', 'term'), pk=pk, is_active=True)
    if not student or not is_basic_exam_student(student) or student.current_class_id != exam.classroom_id or not exam.is_eligible_class():
        messages.error(request, 'This exam is available only to Basic 4 and Basic 6 students.')
        return redirect('student_dashboard')
    now = timezone.now()
    if now < exam.start_time or now >= exam.end_time:
        messages.error(request, 'This exam is not currently available.')
        return redirect('student_dashboard')
    if StudentExamSession.objects.filter(student=student, exam=exam, is_completed=True).exists():
        messages.info(request, 'Your attempt has already been submitted.')
        return redirect('student_dashboard')
    return render(request, 'portal/student_cbt_instructions.html', {'exam': exam, 'student': student})


@login_required(login_url='login')
def cbt_exam_view(request, pk):
    student = getattr(request.user, 'student_record', None)
    exam = get_object_or_404(CBTExam.objects.prefetch_related('questions'), pk=pk, is_active=True)
    if not student or not is_basic_exam_student(student) or student.current_class_id != exam.classroom_id or not exam.is_eligible_class():
        messages.error(request, 'This exam is available only to Basic 4 and Basic 6 students.')
        return redirect('student_dashboard')
    now = timezone.now()
    existing_attempt = CBTAttempt.objects.filter(exam=exam, student=student).first()
    if existing_attempt and existing_attempt.status == 'in_progress' and now >= exam.end_time:
        existing_session = StudentExamSession.objects.filter(exam=exam, student=student).first()
        if existing_session and not existing_session.is_completed:
            _grade_cbt_session(existing_session, exam)
        existing_attempt.status = 'expired'
        existing_attempt.score = int(existing_session.score) if existing_session else 0
        existing_attempt.submitted_at = now
        existing_attempt.save(update_fields=['status', 'score', 'submitted_at'])
        messages.error(request, 'The exam time has expired and your attempt was submitted automatically.')
        return redirect('student_dashboard')
    if now < exam.start_time or now >= exam.end_time:
        messages.error(request, 'This exam is not currently available.')
        return redirect('student_dashboard')
    session, _ = StudentExamSession.objects.get_or_create(student=student, exam=exam)
    attempt, _ = CBTAttempt.objects.get_or_create(exam=exam, student=student)
    deadline = min(exam.end_time, session.start_time + datetime.timedelta(minutes=exam.duration))
    if not session.is_completed and now >= deadline:
        _grade_cbt_session(session, exam)
        if attempt.status == 'in_progress':
            attempt.status = 'expired'
            attempt.score = int(session.score)
            attempt.submitted_at = session.submitted_at
            attempt.save(update_fields=['status', 'score', 'submitted_at'])
        messages.error(request, 'The exam time has expired and your attempt was submitted automatically.')
        return redirect('student_dashboard')
    if session.is_completed:
        messages.info(request, 'Your attempt has already been submitted.')
        return redirect('student_dashboard')
    if request.method == 'POST':
        submitted_responses = request.POST.get('responses')
        if submitted_responses:
            try:
                responses = json.loads(submitted_responses)
            except (TypeError, ValueError):
                responses = {}
        else:
            responses = {
                str(question.pk): request.POST.get(f'question_{question.pk}', '')
                for question in exam.questions.all()
            }
        responses = {str(key): value for key, value in responses.items() if value in {'A', 'B', 'C', 'D'}}
        is_final_submit = request.POST.get('auto_submit') == 'true' or request.POST.get('submit_exam') == 'true' or timezone.now() >= deadline
        with transaction.atomic():
            session.responses = responses
            if is_final_submit:
                total_questions, correct_answers = _grade_cbt_session(session, exam)
            else:
                total_questions = exam.questions.count()
                correct_answers = sum(responses.get(str(question.pk), '') == question.correct_answer for question in exam.questions.all())
                session.score = float(correct_answers)
                session.save(update_fields=['responses', 'score', 'is_completed', 'submitted_at'])
            for question in exam.questions.all():
                CBTResponse.objects.update_or_create(attempt=attempt, question=question, defaults={'answer': responses.get(str(question.pk), '')})
            attempt.score = correct_answers
            attempt.status = 'submitted' if is_final_submit else 'in_progress'
            attempt.submitted_at = session.submitted_at if is_final_submit else None
            attempt.save(update_fields=['score', 'status', 'submitted_at'])
        if not is_final_submit:
            return JsonResponse({'ok': True, 'saved': True, 'responses': responses})
        messages.success(request, 'CBT exam submitted successfully.')
        return redirect('student_dashboard')
    if now >= deadline:
        _grade_cbt_session(session, exam)
        messages.error(request, 'The exam time has expired and your attempt was submitted automatically.')
        return redirect('student_dashboard')
    questions = [{
        'id': question.pk,
        'text': question.question_text,
        'image_url': question.image.url if question.image else '',
        'options': {'A': question.option_a, 'B': question.option_b, 'C': question.option_c, 'D': question.option_d},
    } for question in exam.questions.all()]
    return render(request, 'portal/student_cbt_take.html', {
        'exam': exam,
        'student': student,
        'session': session,
        'questions_json': json.dumps(questions),
        'responses_json': json.dumps(session.responses),
        'deadline_ms': int(timezone.localtime(deadline).timestamp() * 1000),
    })


@login_required(login_url='login')
def reset_cbt_attempt_view(request, pk):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    if principal_action_denied(request):
        return redirect('dashboard')
    attempt = get_object_or_404(CBTAttempt, pk=pk)
    attempt.status = 'in_progress'
    attempt.started_at = timezone.now()
    attempt.submitted_at = None
    attempt.score = 0
    attempt.responses.all().delete()
    attempt.save(update_fields=['status', 'started_at', 'submitted_at', 'score'])
    messages.success(request, 'Student exam attempt reset successfully.')
    return redirect('dashboard')


@login_required(login_url='login')
def result_entry_view(request, student_pk):
    teacher = getattr(request.user, 'teacher_record', None)
    if is_admin_user(request.user):
        student = get_object_or_404(Student, pk=student_pk)
    elif teacher:
        student = get_object_or_404(Student, pk=student_pk, current_class__in=teacher.assigned_class.all())
    else:
        return redirect('dashboard')
    term = AcademicTerm.objects.filter(is_active=True).first()
    if not teacher or not term:
        return redirect('dashboard')
    subjects = valid_subjects(Subject.objects.filter(class_subjects__class_room=student.current_class).distinct()).order_by('name')
    if request.method == 'POST':
        if results_are_locked(student.current_class, term):
            messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
            return redirect('result_entry', student_pk=student.pk)
        for subject in subjects:
            try:
                ca = max(0, min(30, float(request.POST.get(f'ca_{subject.pk}', 0))))
                theory = max(0, min(40, float(request.POST.get(f'theory_{subject.pk}', 0))))
            except (TypeError, ValueError):
                messages.error(request, 'Scores must be valid numbers.')
                return redirect('result_entry', student_pk=student.pk)
            attempt = CBTAttempt.objects.filter(exam__subject=subject, exam__classroom=student.current_class, exam__term=term, student=student, status='submitted').order_by('-submitted_at').first()
            obj = (attempt.score / attempt.exam.questions.count() * 30) if attempt and attempt.exam.questions.count() else 0
            result, _ = SubjectResult.objects.get_or_create(student=student, term=term, subject=subject)
            result.continuous_assessment = ca
            result.cbt_obj = obj
            result.theory = theory
            result.save()
        messages.success(request, 'Results saved successfully.')
        return redirect('report_card', student_pk=student.pk)
    results = {result.subject_id: result for result in SubjectResult.objects.filter(student=student, term=term)}
    for subject in subjects:
        result = results.get(subject.pk) or SubjectResult(student=student, term=term, subject=subject)
        attempt = CBTAttempt.objects.filter(exam__subject=subject, exam__classroom=student.current_class, exam__term=term, student=student, status='submitted').order_by('-submitted_at').first()
        result.cbt_obj = Decimal(attempt.score * 30 / attempt.exam.questions.count()) if attempt and attempt.exam.questions.count() else Decimal('0')
        result.exam_total = result.cbt_obj + result.theory
        result.total = result.continuous_assessment + result.exam_total
        subject.current_result = result
    return render(request, 'portal/result_entry_fixed.html', {'student': student, 'term': term, 'subjects': subjects})


@login_required(login_url='login')
def report_card_view(request, student_pk):
    student = get_object_or_404(Student, pk=student_pk)
    term_id = request.GET.get('term')
    session_id = request.GET.get('session')
    term = AcademicTerm.objects.filter(
        pk=term_id,
        session_id=session_id,
    ).first() if term_id and session_id else AcademicTerm.objects.filter(is_active=True).first()
    if not is_admin_user(request.user):
        parent = getattr(request.user, 'parent_record', None)
        teacher = getattr(request.user, 'teacher_record', None)
        teacher_can_view = teacher and student.current_class_id in teacher.assigned_class.values_list('pk', flat=True)
        if getattr(request.user, 'student_record', None) != student and (not parent or not parent.children.filter(pk=student.pk).exists()) and not teacher_can_view:
            return redirect('dashboard')
    if not term:
        return render(request, 'portal/report_card.html', {'student': student, 'term': None, 'results': []})
    classroom = historical_classroom(student, term)
    outstanding_balance = student_outstanding_balance(student, term)
    if outstanding_balance > 0 and not is_admin_user(request.user):
        return render(request, 'portal/report_locked.html', {
            'student': student,
            'outstanding_balance': outstanding_balance,
            'parent_lock': bool(getattr(request.user, 'parent_record', None)),
        })
    class_publication = ClassResultStatus.objects.filter(
        classroom=classroom,
        term=term,
    ).first() if classroom else None
    published = term.reports_published or bool(class_publication and class_publication.is_published) or is_admin_user(request.user)
    context = _report_card_context(student, term, published=published)
    context['fee_override'] = bool(outstanding_balance > 0 and is_admin_user(request.user))
    context['fee_balance'] = outstanding_balance
    return render(request, 'portal/report_card.html', context)


@login_required(login_url='login')
@role_required(['Admin', 'Principal'])
@user_passes_test(is_admin_user, login_url='dashboard')
def broadsheet_view(request):
    admin_access = is_admin_user(request.user)
    allowed_classrooms = ClassRoom.objects.all()
    classrooms = classroom_progression_order(allowed_classrooms)
    sessions = AcademicSession.objects.order_by('-name')
    terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name')
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else (active_term.session if active_term else None)
    if selected_session:
        terms = terms.filter(session=selected_session)
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else terms.filter(pk=active_term.pk).first() if active_term else terms.filter(is_active=True).first()
    selected_class = classrooms.filter(pk=request.GET.get('classroom')).first() if request.GET.get('classroom') else classrooms.first()
    if request.method == 'POST':
        if not admin_access:
            messages.error(request, 'Only administrators can update broadsheet status.')
            return redirect(request.META.get('HTTP_REFERER', 'broadsheet'))
        selected_term = get_object_or_404(AcademicTerm, pk=request.POST.get('term'))
        action = request.POST.get('action')
        if action == 'approve_broadsheet':
            selected_class = classrooms.filter(pk=request.POST.get('classroom')).first()
            status = ClassResultStatus.objects.filter(classroom=selected_class, term=selected_term).first() if selected_class else None
            if selected_term.broadsheet_approved and (selected_term.reports_published or (status and status.is_live)):
                messages.error(request, 'You must unpublish the broadsheet before you can disapprove it.')
                return redirect(request.META.get('HTTP_REFERER', 'broadsheet'))
            previous_approval = selected_term.broadsheet_approved
            selected_term.broadsheet_approved = not selected_term.broadsheet_approved
            selected_term.save(update_fields=['broadsheet_approved'])
            log_security_action(
                request,
                'BROADSHEET_APPROVED' if selected_term.broadsheet_approved else 'BROADSHEET_DISAPPROVED',
                f'{selected_class.name if selected_class else "Unknown class"} - {selected_term.term_name} {selected_term.session.name}',
                {'before': {'broadsheet_approved': previous_approval}, 'after': {'broadsheet_approved': selected_term.broadsheet_approved}},
            )
            messages.success(request, 'Broadsheet approved.' if selected_term.broadsheet_approved else 'Broadsheet disapproved.')
        return redirect(f"{request.path}?classroom={request.POST.get('classroom', '')}&session={selected_term.session_id}&term={selected_term.pk}")
    subjects = list(valid_subjects(Subject.objects.filter(classroomsubject__class_room=selected_class).distinct()).order_by('name')) if selected_class else []
    result_rows = []
    if selected_class and selected_term:
        students = students_in_term_classroom(selected_term, selected_class)
        results = valid_subject_results(SubjectResult.objects.filter(
            student__in=students,
            term=selected_term,
            term__session=selected_term.session,
        ).select_related('student', 'subject'))
        by_student = {student.pk: {'student': student, 'scores': {}, 'total': Decimal('0')} for student in students}
        for result in results:
            row = by_student.get(result.student_id)
            if not row:
                continue
            row['scores'][result.subject_id] = result
            row['total'] += result.total
        subject_count = len(subjects)
        result_rows = sorted(by_student.values(), key=lambda row: row['total'], reverse=True)
        previous_total = None
        position = 0
        for index, row in enumerate(result_rows, start=1):
            if row['total'] != previous_total:
                position = index
                previous_total = row['total']
            row['position'] = position
            row['percentage'] = ((row['total'] / (subject_count * 100) * 100).quantize(Decimal('0.1')) if subject_count else Decimal('0.0'))
    average = (sum((row['percentage'] for row in result_rows), Decimal('0')) / len(result_rows)).quantize(Decimal('0.1')) if result_rows else Decimal('0.0')
    return render(request, 'portal/broadsheet.html', {'classrooms': classrooms, 'sessions': sessions, 'terms': terms, 'selected_class': selected_class, 'selected_session': selected_session, 'selected_term': selected_term, 'subjects': subjects, 'rows': result_rows, 'class_average': average, 'max_total': len(subjects) * 100, 'selected_classroom': selected_class.pk if selected_class else '', 'selected_session_id': selected_session.pk if selected_session else '', 'selected_term_id': selected_term.pk if selected_term else '', 'terms_json': json.dumps(session_terms_map()), 'broadsheet': {'is_approved': selected_term.broadsheet_approved if selected_term else False, 'is_published': selected_term.reports_published if selected_term else False}, 'can_manage_broadsheet': admin_access})


@login_required(login_url='login')
def save_teacher_comment_view(request):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    if request.method != 'POST':
        return redirect('broadsheet')
    student = get_object_or_404(Student, pk=request.POST.get('student_id'))
    term = get_object_or_404(AcademicTerm, pk=request.POST.get('term'), session_id=request.POST.get('session'))
    classroom = historical_classroom(student, term)
    if results_are_locked(classroom, term):
        messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
        return redirect(f"{reverse('broadsheet')}?classroom={request.POST.get('class', '')}&session={term.session_id}&term={term.pk}")
    previous_comment = student.teacher_comment
    student.teacher_comment = request.POST.get('comment', '').strip()
    student.save(update_fields=['teacher_comment'])
    log_security_action(request, 'COMMENT_MODIFIED', f'{student} - {term.term_name} {term.session.name}', {
        'before': {'teacher_comment': previous_comment}, 'after': {'teacher_comment': student.teacher_comment},
    })
    messages.success(request, 'Teacher comment saved.')
    query = '?classroom={}&session={}&term={}'.format(request.POST.get('class', ''), request.POST.get('session', ''), request.POST.get('term', ''))
    return redirect(f'/results/broadsheet/{query}')


@login_required(login_url='login')
def character_skills_view(request):
    admin_access = is_admin_user(request.user)
    teacher = getattr(request.user, 'teacher_record', None)
    if not admin_access and not teacher:
        messages.error(request, 'Unauthorized access to Character & Skills.')
        return redirect('dashboard')
    allowed_classrooms = ClassRoom.objects.all() if admin_access else teacher.assigned_class.all()
    classrooms = classroom_progression_order(allowed_classrooms)
    sessions = AcademicSession.objects.order_by('-name')
    terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name')
    active_term = AcademicTerm.objects.select_related('session').filter(is_active=True).first()
    filter_data = request.POST if request.method == 'POST' else request.GET
    selected_session = sessions.filter(pk=filter_data.get('session')).first() if filter_data.get('session') else (active_term.session if active_term else None)
    if selected_session:
        terms = terms.filter(session=selected_session)
    selected_term = terms.filter(pk=filter_data.get('term')).first() if filter_data.get('term') else (terms.filter(pk=active_term.pk).first() if active_term else terms.filter(is_active=True).first())
    selected_class = classrooms.filter(pk=filter_data.get('classroom')).first() if filter_data.get('classroom') else classrooms.first()
    if request.method == 'POST':
        if not selected_term:
            messages.error(request, 'Please select an academic term.')
        else:
            student = get_object_or_404(Student, pk=request.POST.get('student_id'))
            classroom = historical_classroom(student, selected_term)
            if classroom not in allowed_classrooms:
                return redirect('dashboard')
            if results_are_locked(classroom, selected_term):
                messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
                return redirect(f"{request.path}?classroom={classroom.pk}&session={selected_term.session_id}&term={selected_term.pk}")
            evaluation_type = request.POST.get('evaluation_type')
            rating_fields = ('attentiveness', 'punctuality', 'self_control', 'relationship_with_others') if evaluation_type == 'character' else ('music', 'indoor_games', 'outdoor_games', 'club_association') if evaluation_type == 'skills' else ()
            if not rating_fields:
                messages.error(request, 'Please select a valid evaluation type.')
                return redirect(request.META.get('HTTP_REFERER', 'character_skills'))
            ratings = {}
            invalid = False
            for field in rating_fields:
                value = request.POST.get(field, '').strip()
                if value:
                    try:
                        value = int(value)
                    except ValueError:
                        invalid = True
                        break
                    if value < 1 or value > 5:
                        invalid = True
                        break
                    ratings[field] = value
                else:
                    ratings[field] = None
            if invalid:
                messages.error(request, 'Ratings must be whole numbers from 1 to 5.')
            else:
                StudentEvaluation.objects.update_or_create(student=student, session=selected_session, term=selected_term, defaults=ratings)
                messages.success(request, 'Character and skills ratings saved.')
        return redirect(f"{request.path}?classroom={request.POST.get('classroom', '')}&session={selected_term.session_id if selected_term else ''}&term={selected_term.pk if selected_term else ''}")
    students = students_in_term_classroom(selected_term, selected_class)
    evaluations = {evaluation.student_id: evaluation for evaluation in StudentEvaluation.objects.filter(student__in=students, session=selected_session, term=selected_term)} if selected_term and selected_session else {}
    return render(request, 'portal/character_skills.html', {'classrooms': classrooms, 'sessions': sessions, 'terms': terms, 'selected_class': selected_class, 'selected_session': selected_session, 'selected_term': selected_term, 'students': students, 'evaluations': evaluations, 'character_traits': [('attentiveness', 'Attentiveness'), ('punctuality', 'Punctuality'), ('self_control', 'Self Control'), ('relationship_with_others', 'Relationship With Others')], 'skill_traits': [('music', 'Music'), ('indoor_games', 'Indoor Games'), ('outdoor_games', 'Outdoor Games'), ('club_association', 'Club/Association')], 'selected_classroom': selected_class.pk if selected_class else '', 'selected_session_id': selected_session.pk if selected_session else '', 'selected_term_id': selected_term.pk if selected_term else '', 'terms_json': json.dumps(session_terms_map()), 'can_manage_evaluations': True})


def automated_comments_view(request):
    if not is_admin_user(request.user):
        messages.error(request, 'Unauthorized access to Automated Comments.')
        return redirect('dashboard')
    if not AutomatedCommentBank.objects.exists():
        default_comments = [
            (90, 100, "Brilliant academic result, but character and conduct need urgent improvement.", "Outstanding performance and commendable behavior. Keep it up!", "An exemplary student in both academics and character. Keep soaring!"),
            (80, 89.99, "Excellent grades, but you must work on your relationship with others.", "Excellent result and very good conduct.", "A brilliant and exceptionally well-behaved student. Proud of you!"),
            (70, 79.99, "Very good academic effort; however, behavior requires attention.", "Very good performance and conduct. Keep pushing higher!", "Very good result paired with outstanding character. Well done!"),
            (60, 69.99, "Good result, but your conduct and punctuality must improve.", "Good result. Continue to work hard on your studies.", "Good result and excellent character. Put more effort into academics!"),
            (50, 59.99, "Fair result. Significant effort is needed in both studies and behavior.", "Fair result. You can definitely do better next term.", "Fair result, but your excellent character is highly commendable."),
            (40, 49.99, "Poor result. You need to wake up, study harder, and improve your conduct.", "Poor result. Please focus more on your studies next term.", "Poor result, though your conduct is stellar. Study harder!"),
            (0, 39.99, "Very poor result. Urgent intervention required in both academics and behavior.", "Very poor result. You must work much harder.", "Very poor result. Let your excellent character reflect in your studies."),
        ]
        AutomatedCommentBank.objects.bulk_create([
            AutomatedCommentBank(min_score=min_score, max_score=max_score, char_poor=char_poor, char_good=char_good, char_excellent=char_excellent)
            for min_score, max_score, char_poor, char_good, char_excellent in default_comments
        ])
    if request.method == 'POST':
        for entry in AutomatedCommentBank.objects.all():
            entry.char_poor = request.POST.get(f'char_poor_{entry.pk}', entry.char_poor)
            entry.char_good = request.POST.get(f'char_good_{entry.pk}', entry.char_good)
            entry.char_excellent = request.POST.get(f'char_excellent_{entry.pk}', entry.char_excellent)
            entry.save(update_fields=['char_poor', 'char_good', 'char_excellent'])
        messages.success(request, 'Comment bank updated successfully.')
        return redirect('automated_comments')
    comment_bank = AutomatedCommentBank.objects.order_by('-min_score')
    return render(request, 'portal/automated_comments.html', {'comment_bank': comment_bank})


def _result_entry_student(request, student_pk):
    teacher = getattr(request.user, 'teacher_record', None)
    if is_admin_user(request.user):
        student = get_object_or_404(Student, pk=student_pk)
    elif teacher:
        student = get_object_or_404(Student, pk=student_pk, current_class__in=teacher.assigned_class.all())
    else:
        return None, None
    terms = AcademicTerm.objects.all()
    term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else terms.filter(is_active=True).first()
    return student, term


def _result_upload_context(request):
    teacher = getattr(request.user, 'teacher_record', None)
    classrooms = classroom_progression_order(ClassRoom.objects.all()) if is_admin_user(request.user) else classroom_progression_order(teacher.assigned_class.all())
    sessions = AcademicSession.objects.order_by('-name')
    terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'term_name')
    active_term = terms.filter(is_active=True).first()
    active_session = active_term.session if active_term else sessions.filter(is_active=True).first()
    selected_class = classrooms.filter(pk=request.GET.get('classroom')).first() if request.GET.get('classroom') else classrooms.first()
    selected_session = sessions.filter(pk=request.GET.get('session')).first() if request.GET.get('session') else active_session
    selected_session = selected_session or active_session
    if selected_session:
        terms = terms.filter(session=selected_session)
    selected_term = terms.filter(pk=request.GET.get('term')).first() if request.GET.get('term') else terms.filter(pk=active_term.pk).first() if active_term else terms.filter(is_active=True).first()
    selected_term = selected_term or terms.first()
    students = students_in_term_classroom(selected_term, selected_class)
    return {
        'classrooms': classrooms,
        'sessions': sessions,
        'terms': terms,
        'selected_class': selected_class,
        'selected_session': selected_session,
        'selected_session_name': selected_session.name if selected_session else '',
        'selected_term': selected_term,
        'selected_term_name': selected_term.term_name if selected_term else '',
        'students': students,
        'terms_json': json.dumps(session_terms_map()),
    }


@login_required(login_url='login')
def ca_results_uploads_view(request):
    return redirect('results_uploads')


@login_required(login_url='login')
def ca_result_entry_view(request, student_pk):
    student, term = _result_entry_student(request, student_pk)
    if not student or not term:
        return redirect('dashboard')
    subjects = valid_subjects(Subject.objects.filter(classroomsubject__class_room=student.current_class).distinct()).order_by('name')
    if request.method == 'POST':
        for subject in subjects:
            try:
                ca = max(0, min(30, float(request.POST.get(f'ca_{subject.pk}', 0))))
            except (TypeError, ValueError):
                messages.error(request, 'Scores must be valid numbers.')
                return redirect('ca_result_entry', student_pk=student.pk)
            result, _ = SubjectResult.objects.get_or_create(student=student, term=term, subject=subject)
            result.continuous_assessment = ca
            result.save()
        messages.success(request, 'CA scores saved successfully.')
        return redirect(f'{reverse("ca_result_entry", args=[student.pk])}?term={term.pk}')
    results = {result.subject_id: result for result in SubjectResult.objects.filter(student=student, term=term)}
    for subject in subjects:
        subject.current_result = results.get(subject.pk) or SubjectResult(student=student, term=term, subject=subject)
    return render(request, 'portal/ca_result_entry.html', {'student': student, 'term': term, 'subjects': subjects})


@login_required(login_url='login')
def ca_bulk_entry_view(request):
    teacher = getattr(request.user, 'teacher_record', None)
    if not is_admin_user(request.user) and not teacher:
        return redirect('dashboard')
    context = _result_upload_context(request)
    selected_class = context['selected_class']
    selected_term = context['selected_term']
    if not selected_class or not selected_term:
        messages.error(request, 'Please select a class and term before opening bulk CA entry.')
        return redirect('ca_results_uploads')
    subjects = valid_subjects(
        Subject.objects.filter(classroomsubject__class_room=selected_class).distinct()
    ).order_by('name')
    students = students_in_term_classroom(selected_term, selected_class)
    if request.method == 'POST':
        if results_are_locked(selected_class, selected_term):
            messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
            return redirect(request.get_full_path())
        scores = {}
        for student in students:
            for subject in subjects:
                raw_score = request.POST.get(f'ca_{student.pk}_{subject.pk}', '0')
                try:
                    scores[(student.pk, subject.pk)] = max(0, min(30, float(raw_score or 0)))
                except (TypeError, ValueError):
                    messages.error(request, 'Scores must be valid numbers between 0 and 30.')
                    return redirect(request.get_full_path())
        with transaction.atomic():
            for student in students:
                for subject in subjects:
                    result, _ = SubjectResult.objects.get_or_create(
                        student=student,
                        term=selected_term,
                        subject=subject,
                    )
                    result.continuous_assessment = scores[(student.pk, subject.pk)]
                    result.save()
        log_security_action(request, 'SCORE_MODIFIED', f'{selected_class.name} - {selected_term.term_name} {selected_term.session.name}', {
            'before': {},
            'after': {'students_updated': students.count(), 'subjects_updated': subjects.count()},
        })
        messages.success(request, 'All class CA scores saved successfully.')
        return redirect(request.get_full_path())
    results = {}
    for result in SubjectResult.objects.filter(
            student__in=students,
            term=selected_term,
            subject__in=subjects,
        ):
        results.setdefault(result.student_id, {})[result.subject_id] = result.continuous_assessment
    context.update({
        'subjects': subjects,
        'students': students,
        'results': results,
    })
    return render(request, 'portal/ca_bulk_entry.html', context)


@login_required(login_url='login')
def exam_results_uploads_view(request):
    teacher = getattr(request.user, 'teacher_record', None)
    if not is_admin_user(request.user) and not teacher:
        return redirect('dashboard')
    return render(request, 'portal/exam_results_uploads.html', _result_upload_context(request))


@login_required(login_url='login')
def exam_result_entry_view(request, student_pk):
    student, term = _result_entry_student(request, student_pk)
    if not student or not term:
        return redirect('dashboard')
    subjects = valid_subjects(Subject.objects.filter(class_subjects__class_room=student.current_class).distinct()).order_by('name')
    if request.method == 'POST':
        if results_are_locked(historical_classroom(student, term), term):
            messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
            return redirect(f'{reverse("ca_result_entry", args=[student.pk])}?term={term.pk}')
        if results_are_locked(historical_classroom(student, term), term):
            messages.error(request, 'Cannot edit scores or comments while results are published or approved. Please unpublish and disapprove the broadsheet first.')
            return redirect(f'{reverse("exam_result_entry", args=[student.pk])}?term={term.pk}')
        for subject in subjects:
            try:
                theory = max(0, min(40, float(request.POST.get(f'theory_{subject.pk}', 0))))
            except (TypeError, ValueError):
                messages.error(request, 'Scores must be valid numbers.')
                return redirect('exam_result_entry', student_pk=student.pk)
            attempt = CBTAttempt.objects.filter(exam__subject=subject, exam__classroom=student.current_class, exam__term=term, student=student, status='submitted').order_by('-submitted_at').first()
            obj = attempt.score * 30 / attempt.exam.questions.count() if attempt and attempt.exam.questions.count() else 0
            result, _ = SubjectResult.objects.get_or_create(student=student, term=term, subject=subject)
            result.cbt_obj = obj
            result.theory = theory
            result.save()
        messages.success(request, 'Exam scores saved successfully.')
        return redirect('report_card', student_pk=student.pk)
    results = {result.subject_id: result for result in SubjectResult.objects.filter(student=student, term=term)}
    for subject in subjects:
        result = results.get(subject.pk) or SubjectResult(student=student, term=term, subject=subject)
        attempt = CBTAttempt.objects.filter(exam__subject=subject, exam__classroom=student.current_class, exam__term=term, student=student, status='submitted').order_by('-submitted_at').first()
        result.cbt_obj = Decimal(attempt.score * 30 / attempt.exam.questions.count()) if attempt and attempt.exam.questions.count() else Decimal('0')
        result.exam_total = result.cbt_obj + result.theory
        result.total = result.continuous_assessment + result.exam_total
        subject.current_result = result
    return render(request, 'portal/exam_result_entry.html', {'student': student, 'term': term, 'subjects': subjects})


@login_required(login_url='login')
def dashboard_view(request):
    today = timezone.localdate()
    active_session = AcademicSession.objects.filter(is_active=True).first()
    active_term = AcademicTerm.objects.filter(is_active=True, session=active_session).first() if active_session else None
    current_week = active_term.weeks.filter(start_date__lte=today, end_date__gte=today).first() if active_term else None
    active_students = Student.objects.filter(status='Student')
    total_students = active_students.count()
    present_today = Attendance.objects.filter(date=today, status='Present', student__status='Student').values('student').distinct().count()
    active_teachers = Teacher.objects.count()
    classroom_attendance = []
    for classroom in ClassRoom.objects.order_by('section', 'level_number', 'name'):
        total = active_students.filter(current_class=classroom).count()
        present = Attendance.objects.filter(
            date=today,
            status='Present',
            classroom=classroom,
            student__status='Student',
        ).values('student').distinct().count()
        classroom_attendance.append({
            'classroom': classroom,
            'total': total,
            'present': present,
            'rate': round((present / total) * 100) if total else 0,
        })
    students = Student.objects.all().order_by('-id')[:5] # Recent 5 students
    
    context = {
        'total_students': total_students,
        'present_today': present_today,
        'active_teachers': active_teachers,
        'total_parents': Parent.objects.count(),
        'today': today,
        'current_week': current_week,
        'attendance_rate': round((present_today / total_students) * 100) if total_students else 0,
        'classroom_attendance': classroom_attendance,
        'students': students,
    }
    return render(request, 'portal/dashboard.html', context)


@login_required(login_url='login')
@user_passes_test(is_admin_user, login_url='dashboard')
def admin_profile_edit(request):
    profile, _ = AccountProfile.objects.get_or_create(user=request.user, defaults={'role': 'bursar'})
    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, 'Enter a valid email address.')
                return redirect('admin_profile_edit')
        request.user.email = email
        request.user.save(update_fields=['first_name', 'last_name', 'email'])
        if request.FILES.get('profile_picture'):
            profile.profile_picture = request.FILES['profile_picture']
            profile.save(update_fields=['profile_picture'])
        messages.success(request, 'Profile updated successfully.')
        return redirect('admin_profile_edit')
    return render(request, 'portal/admin_profile_edit.html', {'profile': profile})


@login_required(login_url='login')
def my_profile_view(request):
    profile, _ = AccountProfile.objects.get_or_create(user=request.user, defaults={'role': 'student'})
    if request.method == 'POST' and request.FILES.get('profile_picture'):
        profile.profile_picture = request.FILES['profile_picture']
        profile.save(update_fields=['profile_picture'])
        messages.success(request, 'Profile picture updated successfully.')
        return redirect('my_profile')

    record = (
        getattr(request.user, 'teacher_record', None)
        or getattr(request.user, 'parent_record', None)
        or getattr(request.user, 'student_record', None)
    )
    identifier = (
        getattr(record, 'staff_id', None)
        or getattr(record, 'parent_id', None)
        or getattr(record, 'student_id', None)
        or request.user.username
    )
    return render(request, 'portal/my_profile.html', {
        'profile': profile,
        'record': record,
        'profile_identifier': identifier,
    })


@login_required(login_url='login')
@user_passes_test(is_admin_user, login_url='dashboard')
def lin_access_management_view(request):
    if request.method == 'POST':
        student = get_object_or_404(Student, pk=request.POST.get('student_id'))
        student.is_lin_visible = request.POST.get('is_lin_visible') == '1'
        student.save(update_fields=['is_lin_visible'])
        return JsonResponse({'ok': True, 'is_lin_visible': student.is_lin_visible})
    query = request.GET.get('q', '').strip()
    students = Student.objects.order_by('last_name', 'first_name', 'student_id')
    if query:
        students = students.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(student_id__icontains=query)
        )
    return render(request, 'portal/lin_access_management.html', {'students': students, 'query': query})


def update_absence_flag(student, selected_date, request=None):
    recent_absences = Attendance.objects.filter(
        student=student,
        status='Absent',
        date__lte=selected_date,
    ).order_by('-date')[:3]
    was_flagged = student.consecutive_absence_flag
    student.consecutive_absence_flag = len(recent_absences) >= 3
    student.save(update_fields=['consecutive_absence_flag'])
    if request and student.consecutive_absence_flag and not was_flagged:
        log_security_action(request, 'TRUANCY_FLAGGED', student, {
            'after': {'recent_unexcused_absences': len(recent_absences), 'flagged_on': selected_date.isoformat()},
        })


def sync_parent_status(parent):
    parent.status = 'Active' if parent.children.exists() else 'Inactive'
    parent.save(update_fields=['status'])


@login_required(login_url='login')
@registrar_required
def parents_view(request):
    parent_context = {
        'parents': Parent.objects.prefetch_related('children').all(),
        'students': Student.objects.filter(status='Student').select_related('parent').order_by('last_name', 'first_name'),
        'available_students': Student.objects.filter(status='Student', parent__isnull=True).order_by('last_name', 'first_name'),
        'linked_students': Student.objects.filter(status='Student', parent__isnull=False).count(),
        'unlinked_students': Student.objects.filter(status='Student', parent__isnull=True).count(),
        'marital_choices': Parent.MARITAL_STATUS_CHOICES,
        'sex_choices': Parent.SEX_CHOICES,
        'state_choices': ['Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'FCT', 'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara'],
    }
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_parent':
            legacy_name = request.POST.get('name', '').strip()
            if legacy_name and not request.POST.get('first_name'):
                name_parts = legacy_name.split()
                request.POST._mutable = True
                request.POST['first_name'] = name_parts[0]
                request.POST['last_name'] = name_parts[-1] if len(name_parts) > 1 else name_parts[0]
                request.POST['middle_name'] = ' '.join(name_parts[1:-1])
            required_parent_fields = ['first_name', 'last_name', 'phone_number', 'sex', 'marital_status', 'address', 'state', 'lga']
            if any(not request.POST.get(field, '').strip() for field in required_parent_fields):
                messages.error(request, 'Please complete all required parent fields before saving.')
                parent_context.update({'parent_form': request.POST, 'open_parent_modal': True})
                return render(request, 'portal/parents.html', parent_context)
            phone_number = request.POST.get('phone_number', '').strip()
            if Parent.objects.filter(phone_number=phone_number).exists():
                messages.error(request, 'This phone number is already registered. Please provide a different number.')
                parent_context.update({'parent_form': request.POST, 'open_parent_modal': True})
                return render(request, 'portal/parents.html', parent_context)
            email = request.POST.get('email', '').strip() or None
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    messages.error(request, 'Please enter a valid parent email address.')
                    parent_context.update({'parent_form': request.POST, 'open_parent_modal': True})
                    return render(request, 'portal/parents.html', parent_context)
            try:
                parent = Parent.objects.create(
                    first_name=request.POST.get('first_name', '').strip(),
                    last_name=request.POST.get('last_name', '').strip(),
                    middle_name=request.POST.get('middle_name', '').strip(),
                    phone_number=phone_number,
                    sex=request.POST.get('sex', '').strip(),
                    email=email,
                    religion=request.POST.get('religion', '').strip() or None,
                    occupation=request.POST.get('occupation', '').strip() or None,
                    marital_status=request.POST.get('marital_status', '').strip(),
                    address=request.POST.get('address', '').strip(),
                    state=request.POST.get('state', '').strip(),
                    lga=request.POST.get('lga', '').strip(),
                    status='Inactive',
                )
                create_portal_account(parent, 'parent', parent.last_name)
                messages.success(request, f'{parent.display_name} was added to the Parents Manager.')
            except (IntegrityError, ValidationError):
                messages.error(request, 'This phone number is already registered or the parent data conflicts with an existing record.')
                parent_context.update({'parent_form': request.POST, 'open_parent_modal': True})
                return render(request, 'portal/parents.html', parent_context)
            return redirect('parents')
        if action == 'link_student':
            parent = get_object_or_404(Parent, pk=request.POST.get('parent'))
            student = get_object_or_404(Student, pk=request.POST.get('student'))
            student.parent = parent
            student.save(update_fields=['parent'])
            sync_parent_status(parent)
            messages.success(request, f'{student} is now linked to {parent.display_name}.')
            return redirect('parents')
        if action == 'unlink_student':
            parent = get_object_or_404(Parent, pk=request.POST.get('parent'))
            student = get_object_or_404(Student, pk=request.POST.get('student'))
            student.parent = None
            student.save(update_fields=['parent'])
            sync_parent_status(parent)
            messages.success(request, f'{student} was unlinked from their parent.')
            return redirect('parents')

    return render(request, 'portal/parents.html', parent_context)


@login_required(login_url='login')
def parent_profile_view(request, pk):
    parent = get_object_or_404(Parent, pk=pk)
    profile_context = {
        'parent': parent,
        'marital_choices': Parent.MARITAL_STATUS_CHOICES,
        'sex_choices': Parent.SEX_CHOICES,
        'status_choices': [('Active', 'Active'), ('Inactive', 'Inactive')],
        'state_choices': ['Abia', 'Adamawa', 'Akwa Ibom', 'Anambra', 'Bauchi', 'Bayelsa', 'Benue', 'Borno', 'Cross River', 'Delta', 'Ebonyi', 'Edo', 'Ekiti', 'Enugu', 'FCT', 'Gombe', 'Imo', 'Jigawa', 'Kaduna', 'Kano', 'Katsina', 'Kebbi', 'Kogi', 'Kwara', 'Lagos', 'Nasarawa', 'Niger', 'Ogun', 'Ondo', 'Osun', 'Oyo', 'Plateau', 'Rivers', 'Sokoto', 'Taraba', 'Yobe', 'Zamfara'],
        'available_students': Student.objects.filter(status='Student').exclude(parent__isnull=False).order_by('last_name', 'first_name'),
    }
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete_parent':
            if principal_action_denied(request):
                return redirect('parent_profile', pk=parent.pk)
            parent.delete()
            messages.success(request, 'Parent deleted successfully.')
            return redirect('parents')
        if action == 'link_student':
            student = get_object_or_404(Student, pk=request.POST.get('student'))
            student.parent = parent
            student.save(update_fields=['parent'])
            sync_parent_status(parent)
            messages.success(request, f'{student} is now linked to {parent.display_name}.')
            return redirect('parent_profile', pk=parent.pk)
        if action == 'unlink_student':
            student = get_object_or_404(Student, pk=request.POST.get('student'), parent=parent)
            student.parent = None
            student.save(update_fields=['parent'])
            sync_parent_status(parent)
            messages.success(request, f'{student} was unlinked from {parent.display_name}.')
            return redirect('parent_profile', pk=parent.pk)
        if action == 'update_parent':
            required_fields = ['first_name', 'last_name', 'phone_number', 'sex', 'marital_status', 'address', 'state', 'lga']
            if any(not request.POST.get(field, '').strip() for field in required_fields):
                messages.error(request, 'Please complete all required parent fields.')
                profile_context['open_edit_modal'] = True
                for field in ['first_name', 'last_name', 'middle_name', 'phone_number', 'email', 'sex', 'religion', 'occupation', 'marital_status', 'address', 'state', 'lga']:
                    if field in request.POST:
                        setattr(parent, field, request.POST.get(field, ''))
                return render(request, 'portal/parent_profile.html', profile_context)
            parent.first_name = request.POST.get('first_name', '').strip()
            parent.last_name = request.POST.get('last_name', '').strip()
            parent.middle_name = request.POST.get('middle_name', '').strip()
            parent.phone_number = request.POST.get('phone_number', '').strip()
            parent.sex = request.POST.get('sex', '').strip()
            parent.email = request.POST.get('email', '').strip() or None
            if parent.email:
                try:
                    validate_email(parent.email)
                except ValidationError:
                    messages.error(request, 'Please enter a valid parent email address.')
                    profile_context['open_edit_modal'] = True
                    for field in ['first_name', 'last_name', 'middle_name', 'phone_number', 'email', 'sex', 'religion', 'occupation', 'marital_status', 'address', 'state', 'lga']:
                        if field in request.POST:
                            setattr(parent, field, request.POST.get(field, ''))
                    return render(request, 'portal/parent_profile.html', profile_context)
            parent.religion = request.POST.get('religion', '').strip() or None
            parent.occupation = request.POST.get('occupation', '').strip() or None
            parent.marital_status = request.POST.get('marital_status', '').strip()
            parent.address = request.POST.get('address', '').strip()
            parent.state = request.POST.get('state', '').strip()
            parent.lga = request.POST.get('lga', '').strip()
            parent.status = 'Active' if parent.children.exists() else 'Inactive'
            try:
                parent.save()
            except (IntegrityError, ValidationError):
                messages.error(request, 'This parent could not be saved because of a duplicate or data conflict.')
                profile_context['open_edit_modal'] = True
                return render(request, 'portal/parent_profile.html', profile_context)
            messages.success(request, 'Parent profile updated successfully.')
            return redirect('parent_profile', pk=parent.pk)
    return render(request, 'portal/parent_profile.html', profile_context)

@login_required(login_url='login')
def students_view(request):
    role = getattr(getattr(request.user, 'account_profile', None), 'role', None)
    teacher = getattr(request.user, 'teacher_record', None) if role == 'teacher' else None
    can_register_students = bool(
        request.user.is_staff or request.user.is_superuser or role == 'registrar' or
        (role == 'teacher' and teacher and teacher.assigned_class.exists())
    )
    if role not in (None,) and not can_register_students:
        return redirect('dashboard')
    if request.method == 'POST':
        if not can_register_students:
            return redirect('dashboard')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        other_name = request.POST.get('other_name', '')
        sex = request.POST.get('sex')
        date_of_birth = request.POST.get('date_of_birth')
        lin = (request.POST.get('lin') or '').strip()
        state_of_origin = request.POST.get('state_of_origin')
        lga_of_origin = request.POST.get('lga_of_origin')
        program = request.POST.get('program')
        class_id = request.POST.get('current_class')
        phone_number = request.POST.get('phone_number', '')
        religion = request.POST.get('religion', '')
        email = request.POST.get('email', '')
        passport = request.FILES.get('passport')
        physically_challenged = True if request.POST.get('physically_challenged') == 'on' else False

        # Validate Email
        if email:
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "Please enter a valid email address.")
                return redirect('students')

        # Handle class selection - auto-assign immediately
        current_class_obj = None
        if class_id:
            try:
                current_class_obj = ClassRoom.objects.get(name=class_id)
            except ClassRoom.DoesNotExist:
                messages.warning(request, "Class not found, student registered without class assignment.")

        cleaned_first_name = (first_name or '').strip()
        cleaned_last_name = (last_name or '').strip()
        cleaned_email = (email or '').strip()
        if cleaned_first_name and cleaned_last_name and date_of_birth:
            duplicate_student = Student.objects.filter(
                first_name__iexact=cleaned_first_name,
                last_name__iexact=cleaned_last_name,
                date_of_birth=date_of_birth,
            ).exists()
            if duplicate_student:
                messages.error(request, 'A student with this profile already exists.')
                return redirect('students')

        if cleaned_email and Student.objects.filter(email__iexact=cleaned_email).exists():
            messages.error(request, 'A student with this email already exists.')
            return redirect('students')

        if lin and Student.objects.filter(lin__iexact=lin).exists():
            messages.error(request, 'A student with this LIN already exists.')
            return redirect('students')

        if role == 'teacher' and teacher:
            current_class_obj = teacher.assigned_class.filter(name=class_id).first()
            if not current_class_obj:
                messages.error(request, 'Please select one of your assigned classes.')
                return redirect('students')
            expected_program = {
                'KG': 'Kindergarten (KG)',
                'Nursery': 'Nursery (NUR)',
                'Primary': 'Primary (PRY)',
            }.get(current_class_obj.section)
            if program != expected_program:
                messages.error(request, 'Please select the program that matches your assigned class.')
                return redirect('students')

        parent = None
        if request.POST.get('parent_first_name', '').strip():
            parent_required_fields = {
                'parent_first_name': 'first name',
                'parent_last_name': 'last name',
                'parent_phone_number': 'phone number',
                'parent_sex': 'sex',
                'parent_marital_status': 'marital status',
                'parent_address': 'address',
                'parent_state': 'state',
                'parent_lga': 'LGA',
            }
            missing_parent_fields = [label for field, label in parent_required_fields.items() if not request.POST.get(field, '').strip()]
            if missing_parent_fields:
                messages.error(request, f"Please complete the new parent's {', '.join(missing_parent_fields)}.")
                return redirect('students')
        try:
            with transaction.atomic():
                if request.POST.get('parent_first_name', '').strip():
                    parent = Parent.objects.create(
                        first_name=request.POST.get('parent_first_name', '').strip(),
                        last_name=request.POST.get('parent_last_name', '').strip(),
                        phone_number=request.POST.get('parent_phone_number', '').strip(),
                        sex=request.POST.get('parent_sex', '').strip(),
                        marital_status=request.POST.get('parent_marital_status', '').strip(),
                        address=request.POST.get('parent_address', '').strip(),
                        state=request.POST.get('parent_state', '').strip(),
                        lga=request.POST.get('parent_lga', '').strip(),
                        email=request.POST.get('parent_email', '').strip() or None,
                        status='Active',
                    )
                    create_portal_account(parent, 'parent', parent.last_name)

                student = Student.objects.create(
                    first_name=cleaned_first_name,
                    last_name=cleaned_last_name,
                    other_name=other_name,
                    sex=sex,
                    date_of_birth=date_of_birth,
                    lin=lin or None,
                    state_of_origin=state_of_origin,
                    lga_of_origin=lga_of_origin,
                    program=program,
                    current_class=current_class_obj,
                    parent=parent,
                    physically_challenged=physically_challenged,
                    phone_number=phone_number,
                    religion=religion,
                    email=cleaned_email or None,
                    passport=passport,
                    status='Student'
                )
                create_portal_account(student, 'student', student.last_name)
        except (IntegrityError, ValidationError, OSError, ValueError):
            messages.error(request, 'The student, parent, or uploaded file could not be saved. Please check the details and try again.')
            return redirect('students')

        if current_class_obj:
            messages.success(request, f'Student registered successfully with auto-generated ID and allocated to {current_class_obj.name}!')
        else:
            messages.success(request, 'Student registered successfully with auto-generated ID!')
        return redirect('students')

    students = (Student.objects.filter(current_class__in=teacher.assigned_class.all(), status='Student').select_related('parent')
                if teacher and role == 'teacher'
                else Student.objects.select_related('parent').all()).order_by('-id')
    context = {
        'students': students,
        'can_register_students': can_register_students,
        'teacher_class_names_json': json.dumps(list(teacher.assigned_class.values_list('name', flat=True))) if teacher else '[]',
        'teacher_program_names_json': json.dumps(sorted({
            {'KG': 'Kindergarten (KG)', 'Nursery': 'Nursery (NUR)', 'Primary': 'Primary (PRY)'}.get(classroom.section)
            for classroom in teacher.assigned_class.all()
            if classroom.section in {'KG', 'Nursery', 'Primary'}
        })) if teacher else '[]',
        'student_counts': {
            'total': students.count(),
            'Student': students.filter(status='Student').count(),
            'Transferred': students.filter(status='Transferred').count(),
            'Expelled': students.filter(status='Expelled').count(),
            'Graduated': students.filter(status='Graduated').count(),
        },
    }
    return render(request, 'portal/students.html', context)

@login_required(login_url='login')
def student_profile_view(request, pk):
    role = getattr(getattr(request.user, 'account_profile', None), 'role', None)
    teacher = getattr(request.user, 'teacher_record', None) if role == 'teacher' else None
    if teacher and not request.user.is_staff and not request.user.is_superuser:
        student = get_object_or_404(Student, pk=pk, current_class__in=teacher.assigned_class.all())
    elif role == 'parent' and hasattr(request.user, 'parent_record'):
        student = get_object_or_404(Student, pk=pk, parent=request.user.parent_record)
    elif role == 'student' and hasattr(request.user, 'student_record'):
        student = get_object_or_404(Student, pk=pk, user=request.user)
    else:
        student = get_object_or_404(Student, pk=pk)
    
    if request.method == 'POST':
        if teacher and not request.user.is_staff and not request.user.is_superuser:
            return redirect('student_profile', pk=student.pk)
        if role not in (None,) and not request.user.is_staff and not request.user.is_superuser and role not in ('admin', 'registrar'):
            return redirect('student_profile', pk=student.pk)
        action = request.POST.get('action')
        
        if action == 'update_details':
            email = request.POST.get('email', '')
            lin = (request.POST.get('lin') or '').strip()
            other_name = (request.POST.get('other_name') or '').strip()

            # Validate Email
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    messages.error(request, "Please enter a valid email address.")
                    return redirect('student_profile', pk=student.pk)

            if not lin:
                messages.error(request, "Please provide the Learner's Identification Number (LIN).")
                return redirect('student_profile', pk=student.pk)
            if not other_name:
                messages.error(request, "Please provide the student's Other Name.")
                return redirect('student_profile', pk=student.pk)

            student.first_name = request.POST.get('first_name')
            student.last_name = request.POST.get('last_name')
            student.other_name = other_name
            student.sex = request.POST.get('sex')
            student.date_of_birth = request.POST.get('date_of_birth')
            student.lin = lin
            student.state_of_origin = request.POST.get('state_of_origin')
            student.lga_of_origin = request.POST.get('lga_of_origin')
            
            student.phone_number = request.POST.get('phone_number', '')
            student.religion = request.POST.get('religion', '')
            student.email = email
            student.physically_challenged = True if request.POST.get('physically_challenged') == 'on' else False
            
            if request.FILES.get('passport'):
                student.passport = request.FILES.get('passport')
                
            try:
                student.save()
            except IntegrityError:
                messages.error(request, 'This student profile conflicts with an existing record.')
                return redirect('student_profile', pk=student.pk)
            messages.success(request, f"Profile for {student.student_id} updated successfully!")
            return redirect('student_profile', pk=student.pk)
            
        elif action == 'update_status':
            new_status = request.POST.get('status')
            if new_status in ['Student', 'Transferred', 'Expelled', 'Graduated']:
                student.status = new_status
                student.save()
                if student.parent_id:
                    sync_parent_status(student.parent)
                messages.success(request, f"Student status updated to {new_status}.")
            return redirect('student_profile', pk=student.pk)
            
        elif action == 'reset_credentials':
            messages.success(request, f"Portal credentials for {student.student_id} have been reset successfully.")
            return redirect('student_profile', pk=student.pk)

    context = {
        'student': student,
    }
    return render(request, 'portal/student_profile.html', context)


@login_required(login_url='login')
def delete_student_view(request, pk):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    if principal_action_denied(request):
        return redirect('students')
    student = get_object_or_404(Student, pk=pk)
    if request.method == 'POST':
        student.delete()
        messages.success(request, 'Student deleted successfully!')
    return redirect('students')


def save_teacher_qualifications(teacher, request):
    schools = request.POST.getlist('qualification_school')
    qualifications = request.POST.getlist('qualification')
    years = request.POST.getlist('qualification_year')
    highest_values = request.POST.getlist('qualification_highest')
    teacher.qualifications.all().delete()
    for index, values in enumerate(zip(schools, qualifications, years)):
        school, qualification, year = values
        if school.strip() and qualification and year.isdigit():
            TeacherQualification.objects.create(
                teacher=teacher,
                school=school.strip(),
                qualification=qualification,
                year=int(year),
                is_highest=index < len(highest_values) and highest_values[index] in {'1', 'on', 'true'},
            )


@login_required(login_url='login')
def teachers_view(request):
    if request.method == 'POST':
        if not request.user.is_staff and not request.user.is_superuser:
            return redirect('dashboard')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        other_name = request.POST.get('other_name', '').strip()
        staff_type = request.POST.get('staff_type', '').strip()
        birth_month = request.POST.get('birth_month', '').strip()
        birth_day = request.POST.get('birth_day', '').strip()
        state_of_origin = request.POST.get('state_of_origin', '').strip()
        lga_of_origin = request.POST.get('lga_of_origin', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()
        passport = request.FILES.get('passport')
        qualification_rows = list(zip(
            request.POST.getlist('qualification_school'),
            request.POST.getlist('qualification'),
            request.POST.getlist('qualification_year'),
        ))
        if not first_name or not last_name or not staff_type or not birth_month or not birth_day or not state_of_origin or not lga_of_origin or not phone_number:
            messages.error(request, 'Please complete all required teacher fields before saving.')
            return redirect('teachers')
        if staff_type.lower() == 'teaching':
            if not qualification_rows or any(
                not school.strip() or not qualification.strip() or not year.strip().isdigit()
                for school, qualification, year in qualification_rows
            ):
                messages.error(request, 'Teaching staff must have complete school, qualification, and year details.')
                return redirect('teachers')
        if Teacher.objects.filter(email__iexact=email).exists():
            messages.error(request, 'A teacher with this email already exists.')
            return redirect('teachers')
            messages.error(request, 'A teacher with this email already exists.')
            return redirect('teachers')

        current_year = datetime.datetime.now().year
        last_teacher = Teacher.objects.order_by('-id').first()
        next_num = (last_teacher.id + 1) if last_teacher else 1
        generated_staff_id = f"FLPA/TCH/{current_year}/{str(next_num).zfill(3)}"

        try:
            teacher = Teacher.objects.create(
                staff_id=generated_staff_id,
                first_name=first_name,
                last_name=last_name,
                other_name=other_name,
                staff_type=staff_type,
                birth_month=birth_month,
                birth_day=birth_day,
                state_of_origin=state_of_origin,
                lga_of_origin=lga_of_origin,
                phone_number=phone_number,
                email=email,
                status='Active',
                passport=passport,
            )
            create_portal_account(teacher, 'teacher', teacher.last_name)
        except (IntegrityError, ValidationError):
            messages.error(request, 'This teacher could not be saved because the email or phone number is already registered.')
            return redirect('teachers')

        save_teacher_qualifications(teacher, request)
        messages.success(request, "Teacher registered successfully!")
        return redirect('teachers')

    teachers = Teacher.objects.all().order_by('-id')
    return render(request, 'portal/teachers.html', {
        'teachers': teachers,
        'staff_counts': {
            'total': teachers.count(),
            'Active': teachers.filter(status='Active').count(),
            'Inactive': teachers.filter(status='Inactive').count(),
            'Teaching': teachers.filter(staff_type__iexact='Teaching').count(),
            'NonTeaching': teachers.exclude(staff_type__iexact='Teaching').count(),
        },
    })

@login_required(login_url='login')
def teacher_profile_view(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        email = request.POST.get('email', teacher.email)
        
        # Validate Email
        if email:
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "Please enter a valid email address.")
                return redirect('teacher_profile', pk=teacher.pk)

        teacher.first_name = request.POST.get('first_name', teacher.first_name)
        teacher.last_name = request.POST.get('last_name', teacher.last_name)
        teacher.other_name = request.POST.get('other_name', teacher.other_name)
        teacher.staff_type = request.POST.get('staff_type', teacher.staff_type)
        teacher.birth_month = request.POST.get('birth_month', teacher.birth_month)
        teacher.birth_day = request.POST.get('birth_day', teacher.birth_day)
        teacher.state_of_origin = request.POST.get('state_of_origin', teacher.state_of_origin)
        teacher.lga_of_origin = request.POST.get('lga_of_origin', teacher.lga_of_origin)
        teacher.phone_number = request.POST.get('phone_number', teacher.phone_number)
        teacher.email = email
        teacher.status = request.POST.get('status', teacher.status)
        
        if 'passport' in request.FILES:
            teacher.passport = request.FILES['passport']
            
        try:
            with transaction.atomic():
                teacher.save()
                save_teacher_qualifications(teacher, request)
        except (IntegrityError, ValidationError, OSError, ValueError):
            messages.error(request, 'This teacher profile could not be saved. Check the image file and try again.')
            return redirect('teacher_profile', pk=teacher.pk)
        messages.success(request, "Teacher profile updated successfully!")
        return redirect('teacher_profile', pk=teacher.pk)
        
    context = {
        'teacher': teacher,
        'days': range(1, 32),
        'qualification_years': range(datetime.datetime.now().year, 1950, -1),
    }
    return render(request, 'portal/teacher_profile.html', context)

@login_required(login_url='login')
def delete_teacher_view(request, pk):
    if not is_admin_user(request.user):
        return redirect('dashboard')
    if principal_action_denied(request):
        return redirect('teachers')
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, "Teacher deleted successfully!")
    return redirect('teachers')

def forgot_password_view(request):
    return render(request, 'portal/forgot_password.html')


def classroom_progression_order(queryset):
    """Order classroom names by school progression instead of alphabetically."""
    progression = [
        'kg 1', 'kg 2', 'nursery 1', 'nursery 2',
        'primary 1', 'primary 2', 'primary 3', 'primary 4',
        'primary 5', 'primary 6', 'basic 1', 'basic 2', 'basic 3',
        'basic 4', 'basic 5', 'basic 6',
    ]
    rank = Case(*[
        When(name__iexact=name, then=Value(index))
        for index, name in enumerate(progression)
    ], default=Value(len(progression)), output_field=IntegerField())
    return queryset.annotate(classroom_progression_rank=rank).order_by('classroom_progression_rank', 'name')


@login_required(login_url='login')
@registrar_required
def student_class_allocation_view(request):
    """Allocate students to classes"""
    if request.method == 'POST':
        if request.POST.get('action') == 'reassign_student':
            student = get_object_or_404(Student, pk=request.POST.get('student_id'))
            classroom = get_object_or_404(ClassRoom, pk=request.POST.get('class_id'))
            student.current_class = classroom
            student.save(update_fields=['current_class'])
            message = f'{student.first_name} {student.last_name} reassigned to {classroom.name}.'
            messages.success(request, message)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'class_name': classroom.name, 'message': message})
            return redirect('student_class_allocation')
        student_id = request.POST.get('student_id')
        class_name = request.POST.get('class_id')  # This is actually the class name (e.g., "Primary 1")
        selected_program = request.POST.get('program')
        
        student = get_object_or_404(Student, id=student_id)
        try:
            # Find the classroom by name
            classroom = ClassRoom.objects.get(name=class_name)
            program_values = {
                'Kindergarten': 'Kindergarten (KG)',
                'Nursery': 'Nursery (NUR)',
                'Primary': 'Primary (PRY)',
            }
            student.current_class = classroom
            student.program = program_values.get(selected_program, student.program)
            student.save()
            messages.success(request, f"{student.first_name} {student.last_name} allocated to {classroom.name} in {student.program}")
        except ClassRoom.DoesNotExist:
            messages.error(request, f"Class '{class_name}' not found.")
        return redirect('student_class_allocation')

    context = {
        'students': Student.objects.filter(status__in=('Active', 'Student')).order_by('-date_enrolled'),
        'all_classes': classroom_progression_order(ClassRoom.objects.all()),
    }
    return render(request, 'portal/student_class_allocation.html', context)


@login_required(login_url='login')
@teacher_required
def attendance_view(request):
    sessions = AcademicSession.objects.order_by('-name')
    all_terms = AcademicTerm.objects.select_related('session').order_by('-session__name', 'start_date', 'pk')
    active_term = all_terms.filter(is_active=True).first()
    filter_data = request.POST if request.method == 'POST' else request.GET
    session = sessions.filter(pk=filter_data.get('session')).first() if filter_data.get('session') else (active_term.session if active_term else None)
    terms = all_terms.filter(session=session) if session else AcademicTerm.objects.none()
    selected_term = terms.filter(pk=filter_data.get('term')).first() if filter_data.get('term') else terms.filter(pk=active_term.pk).first() if active_term else None
    selected_term = selected_term or terms.first()
    role_profile = getattr(request.user, 'account_profile', None)
    teacher_record = getattr(request.user, 'teacher_record', None) if role_profile and role_profile.role == 'teacher' else None
    if role_profile and role_profile.role == 'teacher':
        classrooms = teacher_record.assigned_class.all() if teacher_record else ClassRoom.objects.none()
    else:
        classrooms = ClassRoom.objects.all()
    classrooms = classrooms.order_by('section', 'level_number', 'name')
    day_choices = [(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday')]
    selected_class_id = request.POST.get('classroom') or request.GET.get('classroom')
    selected_week_id = request.POST.get('week') or request.GET.get('week')
    selected_day_value = request.POST.get('day') or request.GET.get('day')
    if not selected_class_id and role_profile and role_profile.role == 'teacher' and teacher_record:
        assigned_classrooms = teacher_record.assigned_class.all()
        if assigned_classrooms.count() == 1:
            selected_class_id = str(assigned_classrooms.first().pk)
    selected_class = None
    selected_week = None
    selected_date = None
    selected_day = None

    def invalid_id(value):
        return value in (None, '', 'None') or not str(value).isdigit()

    if not session or not selected_term:
        messages.warning(request, 'Select an academic session and term before taking attendance.')
    elif request.method == 'POST' and request.POST.get('action') == 'save_attendance':
        if invalid_id(selected_class_id) or invalid_id(selected_week_id) or selected_day_value not in {str(day) for day, _ in day_choices}:
            messages.error(request, 'Please select a valid classroom, academic week, and school day.')
            return redirect('attendance')
        selected_class = get_object_or_404(classrooms, pk=int(selected_class_id))
        selected_week = get_object_or_404(AcademicWeek, pk=int(selected_week_id), term=selected_term)
        selected_day = int(selected_day_value)
        selected_date = selected_week.start_date + datetime.timedelta(days=selected_day)
        if Holiday.objects.filter(term=selected_term, date=selected_date).exists():
            messages.error(request, 'Attendance cannot be recorded on an academic holiday.')
        else:
            students = list(students_in_term_classroom(selected_term, selected_class))
            allowed_statuses = {value for value, _ in Attendance.STATUS_CHOICES}
            submitted_statuses = [request.POST.get(f'status_{student.pk}', 'Present') for student in students]
            if any(status not in allowed_statuses for status in submitted_statuses):
                messages.error(request, 'One or more attendance statuses are invalid.')
                return redirect(f'{request.path}?classroom={selected_class.pk}&week={selected_week.pk}&day={selected_day}')
            with transaction.atomic():
                register, _ = AttendanceRegister.objects.get_or_create(
                    classroom=selected_class,
                    session=session,
                    date=selected_date,
                )
                for index, student in enumerate(students):
                    Attendance.objects.update_or_create(
                        student=student,
                        classroom=selected_class,
                        session=session,
                        date=selected_date,
                        defaults={
                            'register': register,
                            'status': submitted_statuses[index],
                        },
                    )
                for student in students:
                    update_absence_flag(student, selected_date, request)
            messages.success(request, 'Attendance register updated successfully!')
            return redirect(f'{request.path}?classroom={selected_class.pk}&week={selected_week.pk}&day={selected_day}')
    elif selected_term:
        if selected_class_id in ('', 'None'):
            messages.error(request, 'Please select a valid classroom.')
        elif selected_class_id is not None:
            if invalid_id(selected_class_id):
                messages.error(request, 'Please select a valid classroom.')
            else:
                selected_class = classrooms.filter(pk=int(selected_class_id)).first()
        if selected_week_id in ('', 'None'):
            messages.error(request, 'Please select a valid academic week.')
        elif selected_week_id is not None:
            if invalid_id(selected_week_id):
                messages.error(request, 'Please select a valid academic week.')
            else:
                selected_week = AcademicWeek.objects.filter(pk=int(selected_week_id), term=selected_term).first()
        if selected_day_value in ('', 'None'):
            messages.error(request, 'Please select a valid school day.')
        elif selected_day_value is not None:
            if selected_day_value not in {str(day) for day, _ in day_choices}:
                messages.error(request, 'Please select a valid school day.')
            else:
                selected_day = int(selected_day_value)
        if selected_week and selected_day is not None:
            selected_date = selected_week.start_date + datetime.timedelta(days=selected_day)

    students = list(students_in_term_classroom(selected_term, selected_class)) if selected_class else []
    attendance_statuses = {}
    attendance_recorded = False
    if selected_class and selected_date:
        attendance_statuses = dict(Attendance.objects.filter(
            classroom=selected_class,
            session=session,
            date=selected_date,
        ).values_list('student_id', 'status'))
        attendance_recorded = bool(attendance_statuses)
    for student in students:
        student.attendance_status = attendance_statuses.get(student.pk, 'Present')
    day_options = [
        {
            'value': day,
            'label': label,
            'date': selected_week.start_date + datetime.timedelta(days=day) if selected_week else None,
        }
        for day, label in day_choices
    ]
    context = {
        'classrooms': classrooms,
        'sessions': sessions,
        'terms': terms,
        'terms_json': json.dumps(session_terms_map()),
        'selected_session': session,
        'selected_term': selected_term,
        'current_session': session,
        'active_term': selected_term,
        'weeks': selected_term.weeks.all() if selected_term else [],
        'day_options': day_options,
        'selected_class': selected_class,
        'selected_class_id': selected_class_id,
        'selected_week': selected_week,
        'selected_week_id': selected_week_id,
        'selected_day': selected_day,
        'selected_date': selected_date,
        'students': students,
        'status_choices': Attendance.STATUS_CHOICES,
        'attendance_statuses': attendance_statuses,
        'attendance_recorded': attendance_recorded,
    }
    return render(request, 'portal/attendance.html', context)


@login_required(login_url='login')
def clear_attendance_view(request):
    if not request.user.is_superuser:
        messages.error(request, 'Only Super Admins can clear attendance registers.')
        return redirect('attendance')
    if request.method != 'POST':
        return redirect('attendance')
    classroom = get_object_or_404(ClassRoom, pk=request.POST.get('classroom'))
    attendance_date = parse_date(request.POST.get('date'))
    if not attendance_date:
        messages.error(request, 'Please provide a valid attendance date.')
        return redirect('attendance')
    with transaction.atomic():
        Attendance.objects.filter(classroom=classroom, date=attendance_date).delete()
        AttendanceRegister.objects.filter(classroom=classroom, date=attendance_date).delete()
    messages.success(request, 'Attendance register cleared successfully.')
    query = f'?classroom={classroom.pk}&week={request.POST.get("week", "")}&day={request.POST.get("day", "")}'
    return redirect(f'{request.path.replace("clear-attendance/", "attendance/")}{query}')

def staff_class_allocation_view(request):
    """Allocate teachers (staff) to classes"""
    if request.method == 'POST':
        with transaction.atomic():
            for key, value in request.POST.items():
                if key.startswith('teacher_'):
                    class_id = key.split('_', 1)[1]
                    classroom = ClassRoom.objects.filter(id=class_id).first()
                    if classroom and (not value or Teacher.objects.filter(id=value, staff_type__iexact='Teaching').exists()):
                        classroom.class_teacher_id = value or None
                        classroom.save(update_fields=['class_teacher'])
        messages.success(request, 'All class teacher allocations updated successfully!')
        return redirect('staff_class_allocation')

    # Sorting: KG=1, Nursery=2, Primary=3
    classrooms = ClassRoom.objects.annotate(
        section_order=Case(
            When(section='KG', then=Value(1)),
            When(section='Nursery', then=Value(2)),
            When(section='Primary', then=Value(3)),
            output_field=IntegerField(),
        )
    ).order_by('section_order', 'level_number')
    
    context = {
        'classrooms': classrooms,
        'teachers': Teacher.objects.filter(
            staff_type__iexact='Teaching',
            status__iexact='Active',
        ).order_by('last_name', 'first_name'),
    }
    return render(request, 'portal/staff_class_allocation.html', context)


# ============================================================================
# Web Push Notification Endpoints
# ============================================================================

@login_required(login_url='login')
@require_POST
def register_push_subscription_view(request):
    """
    Register a new push subscription for the current user.
    Expects JSON POST with: endpoint, p256dh, auth
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    endpoint = data.get('endpoint')
    p256dh = data.get('p256dh')
    auth = data.get('auth')

    if not all([endpoint, p256dh, auth]):
        return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

    try:
        subscription, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={
                'p256dh': p256dh,
                'auth': auth,
                'is_active': True,
            }
        )
        return JsonResponse({
            'success': True,
            'message': 'Push subscription registered' if created else 'Push subscription updated',
            'subscription_id': subscription.id,
        })
    except IntegrityError:
        return JsonResponse({'success': False, 'error': 'Subscription endpoint already registered'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='login')
@require_POST
def unregister_push_subscription_view(request):
    """
    Unregister a push subscription for the current user.
    Expects JSON POST with: endpoint
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    endpoint = data.get('endpoint')
    if not endpoint:
        return JsonResponse({'success': False, 'error': 'Missing endpoint'}, status=400)

    try:
        subscription = PushSubscription.objects.get(user=request.user, endpoint=endpoint)
        subscription.delete()
        return JsonResponse({'success': True, 'message': 'Push subscription removed'})
    except PushSubscription.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Subscription not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='login')
def get_vapid_public_key_view(request):
    """
    Retrieve the VAPID public key for client-side subscription.
    This is needed by the service worker to request push notifications.
    """
    vapid_public_key = settings.VAPID_PUBLIC_KEY
    if not vapid_public_key:
        return JsonResponse(
            {'error': 'VAPID public key not configured'},
            status=500
        )
    return JsonResponse({'vapid_public_key': vapid_public_key})
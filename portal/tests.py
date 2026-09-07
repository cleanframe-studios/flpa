import datetime
import re

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AcademicSession, AcademicTerm, AcademicWeek, AdmissionCampaign, Applicant, Attendance, AttendanceRegister, AccountProfile, AuditLog, CBTAttempt, CBTExam, CBTQuestion, CBTResponse, ClassRoom, ClassRoomSubject, FeeStructure, Parent, Student, StudentExamSession, Subject, SubjectResult, StudentFeeAccount, StudentTermRecord, Teacher, TermEnrollment


class AdmissionApprovalWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='registrar', password='pass123')
        AccountProfile.objects.create(user=self.user, role='registrar')
        self.client.force_login(self.user)
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term')
        campaign = AdmissionCampaign.objects.create(
            campaign_name='2026 Admissions',
            target_session=session,
            target_term=term,
            deadline=timezone.now() + datetime.timedelta(days=30),
        )
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        self.applicant = Applicant.objects.create(
            campaign=campaign,
            first_name='Ada',
            last_name='Lovelace',
            sex='Female',
            date_of_birth=datetime.date(2018, 4, 12),
            state_of_origin='Lagos',
            lga='Ikeja',
            intended_class=classroom,
            parent_name='Grace Lovelace',
            parent_phone='08012345678',
            parent_email='grace@example.com',
            payment_status='Verified',
        )

    def test_application_number_is_structured_readable_and_unique(self):
        match = re.fullmatch(r'FLA-26-PRIMARY1-([A-HJ-KM-NP-Z2-9]{6})', self.applicant.temp_reg_number)
        self.assertIsNotNone(match)
        self.assertNotRegex(match.group(1), r'[ILO01]')

        second_applicant = Applicant.objects.create(
            campaign=self.applicant.campaign,
            first_name='Grace',
            last_name='Hopper',
            intended_class=self.applicant.intended_class,
        )
        self.assertNotEqual(self.applicant.temp_reg_number, second_applicant.temp_reg_number)

    def test_approval_creates_and_links_parent_profile(self):
        response = self.client.post(reverse('review_applicants'), {
            'action': 'approve_enroll',
            'applicant_id': self.applicant.pk,
        })

        self.assertRedirects(response, reverse('review_applicants'))
        applicant = Applicant.objects.get(pk=self.applicant.pk)
        parent = applicant.provisioned_parent
        student = applicant.enrolled_student
        self.assertIsNotNone(parent)
        self.assertIsNotNone(student)
        self.assertEqual(student.parent, parent)
        self.assertEqual(parent.first_name, 'Grace')
        self.assertEqual(parent.last_name, 'Lovelace')
        self.assertEqual(applicant.student_id, student.student_id)
        self.assertEqual(applicant.parent_id, parent.parent_id)
        self.assertRegex(parent.parent_id, r'^FLA/PAR/2026/\d{3}$')

    def test_revoke_deletes_generated_profiles_and_returns_to_verified(self):
        self.client.post(reverse('review_applicants'), {
            'action': 'approve_enroll',
            'applicant_id': self.applicant.pk,
        })
        applicant = Applicant.objects.get(pk=self.applicant.pk)
        student_id = applicant.enrolled_student_id
        parent_id = applicant.provisioned_parent_id

        response = self.client.post(reverse('revoke_admission', args=[applicant.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        applicant.refresh_from_db()
        self.assertEqual(applicant.admission_status, 'Verified')
        self.assertIsNone(applicant.enrolled_student)
        self.assertIsNone(applicant.provisioned_parent)
        self.assertEqual(applicant.student_id, '')
        self.assertEqual(applicant.parent_id, '')
        self.assertFalse(Student.objects.filter(pk=student_id).exists())
        self.assertFalse(Parent.objects.filter(pk=parent_id).exists())


class AcademicCalendarGuardTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='admin', password='adminpass123', is_staff=True)
        self.client.force_login(self.user)

    def test_duplicate_session_creation_shows_error_message(self):
        AcademicSession.objects.create(name='2026/2027', is_active=True)

        response = self.client.post(
            reverse('academic_calendar'),
            {'action': 'create_session', 'name': '2026/2027'},
            follow=True,
        )

        self.assertContains(response, 'This Academic Session has already been created.')

    def test_audit_log_is_immutable_and_visible_to_superusers(self):
        superuser = get_user_model().objects.create_superuser(username='audit-superuser', password='pass', email='audit@example.com')
        audit_log = AuditLog.objects.create(
            user=superuser,
            action_type='RESULT_PUBLISHED',
            target_description='Primary 4 - First Term 2026/2027',
            ip_address='127.0.0.1',
            changes_json={'before': {'is_published': False}, 'after': {'is_published': True}},
        )
        self.client.force_login(superuser)

        response = self.client.get(reverse('admin_audit_logs'))

        self.assertContains(response, 'Primary 4 - First Term 2026/2027')
        audit_log.target_description = 'Altered'
        with self.assertRaises(ValueError):
            audit_log.save()

    def test_audit_log_dashboard_rejects_regular_staff(self):
        staff_user = get_user_model().objects.create_user(username='staff-user', password='pass', is_staff=True)
        self.client.force_login(staff_user)

        response = self.client.get(reverse('admin_audit_logs'))

        self.assertRedirects(response, f"{reverse('dashboard')}?next={reverse('admin_audit_logs')}")

    def test_admin_role_has_universal_role_decorator_access(self):
        admin_user = get_user_model().objects.create_user(username='role-admin', password='pass')
        AccountProfile.objects.create(user=admin_user, role='admin')
        self.client.force_login(admin_user)

        audit_response = self.client.get(reverse('admin_audit_logs'))
        results_response = self.client.get(reverse('results_process'))

        self.assertEqual(audit_response.status_code, 200)
        self.assertNotRedirects(results_response, reverse('dashboard'))

    def test_admin_user_roles_updates_profile_and_creates_audit_log(self):
        superuser = get_user_model().objects.create_superuser(username='role-superuser', password='pass', email='roles@example.com')
        target_user = get_user_model().objects.create_user(username='finance-user', password='pass')
        AccountProfile.objects.create(user=target_user, role='teacher')
        self.client.force_login(superuser)

        response = self.client.post(reverse('admin_user_roles'), {'user_id': target_user.pk, 'role': 'bursar'}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccountProfile.objects.get(user=target_user).role, 'bursar')
        self.assertContains(response, 'Role updated for finance-user.')
        self.assertTrue(AuditLog.objects.filter(user=superuser, action_type='ROLE_CHANGED', target_description='finance-user').exists())

    def test_admin_user_roles_assigns_multiple_staff_roles(self):
        superuser = get_user_model().objects.create_superuser(username='multi-role-superuser', password='pass', email='multi@example.com')
        target_user = get_user_model().objects.create_user(username='multi-role-user', password='pass')
        AccountProfile.objects.create(user=target_user, role='teacher')
        self.client.force_login(superuser)

        response = self.client.post(reverse('admin_user_roles'), {'user_id': target_user.pk, 'roles': ['teacher', 'bursar']}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(target_user.groups.values_list('name', flat=True)), {'Bursar', 'Teacher'})
        self.assertEqual(set(AuditLog.objects.get(user=superuser, action_type='ROLE_CHANGED').changes_json['after']['roles']), {'bursar', 'teacher'})

    def test_admin_user_roles_displays_only_staff_accounts(self):
        superuser = get_user_model().objects.create_superuser(username='roles-list-superuser', password='pass', email='roles-list@example.com')
        teacher_user = get_user_model().objects.create_user(username='teacher-user', password='pass')
        parent_user = get_user_model().objects.create_user(username='parent-user', password='pass')
        student_user = get_user_model().objects.create_user(username='student-user', password='pass')
        debug_user = get_user_model().objects.create_user(username='profile-debug-user', password='pass', is_staff=True)
        AccountProfile.objects.create(user=teacher_user, role='teacher')
        AccountProfile.objects.create(user=parent_user, role='parent')
        AccountProfile.objects.create(user=student_user, role='student')
        self.client.force_login(superuser)

        response = self.client.get(reverse('admin_user_roles'))

        self.assertContains(response, 'teacher-user')
        self.assertNotContains(response, 'parent-user')
        self.assertNotContains(response, 'student-user')
        self.assertNotContains(response, 'profile-debug-user')

    def test_result_processing_rejects_bursar_role(self):
        bursar_user = get_user_model().objects.create_user(username='bursar-user', password='pass')
        AccountProfile.objects.create(user=bursar_user, role='bursar')
        self.client.force_login(bursar_user)

        response = self.client.get(reverse('results_process'))

        self.assertRedirects(response, reverse('dashboard'))

    def test_report_card_context_uses_attendance_within_selected_term_dates(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True, reports_published=True)
        week = AcademicWeek.objects.create(term=term, week_number=1, start_date=datetime.date(2026, 9, 7), end_date=datetime.date(2026, 9, 11))
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        register = AttendanceRegister.objects.create(classroom=classroom, session=session, date=week.start_date)
        Attendance.objects.create(register=register, student=student, classroom=classroom, session=session, date=week.start_date, status='Present')

        response = self.client.get(reverse('report_card', args=[student.pk]), {'session': session.pk, 'term': term.pk})

        self.assertEqual(response.context['days_school_opened'], 5)
        self.assertEqual(response.context['days_present'], 1)

    def test_bursar_cannot_access_attendance_manager(self):
        bursar_user = get_user_model().objects.create_user(username='attendance-bursar', password='pass')
        AccountProfile.objects.create(user=bursar_user, role='bursar')
        self.client.force_login(bursar_user)

        response = self.client.get(reverse('attendance'))

        self.assertRedirects(response, reverse('dashboard'))

    def test_attendance_absences_raise_a_truancy_audit_event(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        week = AcademicWeek.objects.create(term=term, week_number=1, start_date=datetime.date(2026, 9, 7), end_date=datetime.date(2026, 9, 11))
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)

        for day in range(3):
            self.client.post(reverse('attendance'), {
                'action': 'save_attendance', 'session': session.pk, 'term': term.pk,
                'classroom': classroom.pk, 'week': week.pk, 'day': day,
                f'status_{student.pk}': 'Absent',
            })

        student.refresh_from_db()
        self.assertTrue(student.consecutive_absence_flag)
        self.assertTrue(AuditLog.objects.filter(action_type='TRUANCY_FLAGGED', target_description=str(student)).exists())

    def test_admin_profile_edit_updates_user_details_and_picture(self):
        picture = SimpleUploadedFile('profile.gif', b'GIF87a', content_type='image/gif')

        response = self.client.post(reverse('admin_profile_edit'), {
            'first_name': 'Ada', 'last_name': 'Admin', 'email': 'ada@example.com', 'profile_picture': picture,
        }, follow=True)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Ada')
        self.assertEqual(self.user.last_name, 'Admin')
        self.assertEqual(self.user.email, 'ada@example.com')
        self.assertTrue(self.user.account_profile.profile_picture.name)
        self.assertContains(response, 'Profile updated successfully.')

    def test_staff_class_allocation_bulk_save_updates_all_submitted_classrooms(self):
        first_teacher = Teacher.objects.create(first_name='Ada', last_name='Lovelace', staff_type='Teaching', phone_number='08000000000', email='ada@example.com')
        second_teacher = Teacher.objects.create(first_name='Grace', last_name='Hopper', staff_type='Teaching', phone_number='08000000001', email='grace@example.com')
        first_class = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1, class_teacher=first_teacher)
        second_class = ClassRoom.objects.create(name='Primary 2', section='Primary', level_number=2)

        response = self.client.post(reverse('staff_class_allocation'), {
            f'teacher_{first_class.pk}': second_teacher.pk,
            f'teacher_{second_class.pk}': '',
        }, follow=True)

        first_class.refresh_from_db()
        second_class.refresh_from_db()
        self.assertEqual(first_class.class_teacher, second_teacher)
        self.assertIsNone(second_class.class_teacher)
        self.assertContains(response, 'All class teacher allocations updated successfully!')

    def test_calendar_terms_are_limited_to_the_active_session(self):
        active_session = AcademicSession.objects.create(name='2027/2028', is_active=True)
        inactive_session = AcademicSession.objects.create(name='2026/2027', is_active=False)
        active_term = AcademicTerm.objects.create(session=active_session, term_name='First Term')
        AcademicTerm.objects.create(session=inactive_session, term_name='Second Term')

        response = self.client.get(reverse('academic_calendar'))

        self.assertQuerySetEqual(response.context['terms'], [active_term])

    def test_active_academic_lists_exclude_graduated_and_inactive_students(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        active_student = Student.objects.create(first_name='Active', last_name='Student', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, status='Active')
        graduated_student = Student.objects.create(first_name='Graduated', last_name='Student', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, status='Graduated')
        inactive_student = Student.objects.create(first_name='Transferred', last_name='Student', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, status='Transferred')
        SubjectResult.objects.create(student=active_student, term=term, subject=Subject.objects.create(name='Science'))
        SubjectResult.objects.create(student=graduated_student, term=term, subject=Subject.objects.get(name='Science'))
        SubjectResult.objects.create(student=inactive_student, term=term, subject=Subject.objects.get(name='Science'))
        TermEnrollment.objects.create(student=active_student, term=term, classroom=classroom)
        TermEnrollment.objects.create(student=graduated_student, term=term, classroom=classroom)
        TermEnrollment.objects.create(student=inactive_student, term=term, classroom=classroom)

        result_response = self.client.get(reverse('results_process'), {'session': session.pk, 'term': term.pk, 'classroom': classroom.pk})
        enrollment_response = self.client.get(reverse('term_enrollment'))
        allocation_response = self.client.get(reverse('student_class_allocation'))

        self.assertEqual([row['student'] for row in result_response.context['student_summaries']], [active_student])
        self.assertQuerySetEqual(enrollment_response.context['enrollments'], [TermEnrollment.objects.get(student=active_student, term=term)])
        self.assertQuerySetEqual(allocation_response.context['students'], [active_student])

    def test_historical_results_use_term_enrollment_classroom(self):
        historical_session = AcademicSession.objects.create(name='2025/2026')
        historical_term = AcademicTerm.objects.create(session=historical_session, term_name='Third Term', reports_published=True)
        active_session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        AcademicTerm.objects.create(session=active_session, term_name='First Term', is_active=True)
        historical_classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        current_classroom = ClassRoom.objects.create(name='Primary 5', section='Primary', level_number=5)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=current_classroom)
        TermEnrollment.objects.create(student=student, term=historical_term, classroom=historical_classroom)
        SubjectResult.objects.create(student=student, term=historical_term, subject=Subject.objects.create(name='Mathematics'))

        response = self.client.get(reverse('results_process'), {'session': historical_session.pk, 'term': historical_term.pk, 'classroom': historical_classroom.pk})

        self.assertEqual([row['student'] for row in response.context['student_summaries']], [student])

        user = get_user_model().objects.create_user(username='historical-report-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        self.client.force_login(user)

        response = self.client.get(reverse('student_report_hub'), {'session': historical_session.pk, 'term': historical_term.pk})

        self.assertContains(response, 'View Report Card')

    def test_historical_result_views_fall_back_to_stored_scores_without_enrollments(self):
        historical_session = AcademicSession.objects.create(name='2025/2026')
        historical_term = AcademicTerm.objects.create(session=historical_session, term_name='Third Term')
        active_session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        AcademicTerm.objects.create(session=active_session, term_name='First Term', is_active=True)
        historical_classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        current_classroom = ClassRoom.objects.create(name='Primary 5', section='Primary', level_number=5)
        subject = Subject.objects.create(name='Mathematics')
        unscored_subject = Subject.objects.create(name='English')
        ClassRoomSubject.objects.create(class_room=historical_classroom, subject=subject)
        ClassRoomSubject.objects.create(class_room=historical_classroom, subject=unscored_subject)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=current_classroom)
        SubjectResult.objects.create(student=student, term=historical_term, subject=subject)
        query = {'session': historical_session.pk, 'term': historical_term.pk, 'classroom': historical_classroom.pk}

        process_response = self.client.get(reverse('results_process'), query)
        upload_response = self.client.get(reverse('results_uploads'), query)
        broadsheet_response = self.client.get(reverse('broadsheet'), query)

        self.assertEqual([row['student'] for row in process_response.context['student_summaries']], [student])
        self.assertQuerySetEqual(upload_response.context['students'], [student])
        self.assertEqual([row['student'] for row in broadsheet_response.context['rows']], [student])
        self.assertEqual(upload_response.context['results'][student.pk][unscored_subject.pk].total, 0)

    def test_teacher_student_directory_excludes_graduated_students(self):
        teacher = Teacher.objects.create(first_name='Ada', last_name='Lovelace', staff_type='Teaching', phone_number='08000000000', email='teacher@example.com')
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4, class_teacher=teacher)
        active_student = Student.objects.create(first_name='Active', last_name='Student', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, status='Student')
        graduated_student = Student.objects.create(first_name='Graduated', last_name='Student', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, status='Graduated')
        user = get_user_model().objects.create_user(username='directory-teacher', password='pass')
        teacher.user = user
        teacher.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='teacher')
        self.client.force_login(user)

        response = self.client.get(reverse('students'))

        self.assertQuerySetEqual(response.context['students'], [active_student])

    def test_calendar_shows_empty_state_for_active_session_without_terms(self):
        AcademicSession.objects.create(name='2027/2028', is_active=True)

        response = self.client.get(reverse('academic_calendar'))

        self.assertContains(response, "No terms created for 2027/2028 yet. Click 'Create Term' to set them up.")

    def test_term_enrollment_synchronizes_existing_enrollment_to_current_class(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        previous_class = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        promoted_class = ClassRoom.objects.create(name='Primary 6', section='Primary', level_number=6)
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
            current_class=previous_class, status='Active',
        )
        enrollment = TermEnrollment.objects.create(student=student, term=term, classroom=previous_class)
        student.current_class = promoted_class
        student.save(update_fields=['current_class'])

        response = self.client.post(reverse('term_enrollment'), follow=True)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.classroom, promoted_class)
        self.assertContains(response, '1 enrollment(s) synchronized')

    def test_parent_manager_creates_and_links_parent_to_student(self):
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom,
        )
        response = self.client.post(reverse('parents'), {
            'action': 'create_parent', 'name': 'Grace Lovelace', 'phone_number': '08000000000',
            'sex': 'Female', 'email': '', 'religion': 'Christianity', 'occupation': 'Engineer',
            'marital_status': 'Married', 'address': 'One Main Street', 'state': 'Lagos', 'lga': 'Ikeja',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        parent = Parent.objects.get(name='Grace Lovelace')
        self.client.post(reverse('parents'), {'action': 'link_student', 'parent': parent.pk, 'student': student.pk})
        student.refresh_from_db()
        self.assertEqual(student.parent, parent)

    def test_parent_manager_rejects_missing_sex(self):
        response = self.client.post(reverse('parents'), {
            'action': 'create_parent', 'first_name': 'Grace', 'last_name': 'Lovelace',
            'phone_number': '08000000000', 'sex': '', 'marital_status': 'Married',
            'address': 'One Main Street', 'state': 'Lagos', 'lga': 'Ikeja',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please complete all required parent fields before saving.')
        self.assertFalse(Parent.objects.filter(first_name='Grace', last_name='Lovelace').exists())

    def test_new_student_gets_role_account_with_lowercase_surname_password(self):
        classroom = ClassRoom.objects.create(name='Basic 4', section='Primary', level_number=4)
        self.client.post(reverse('students'), {
            'first_name': 'Ada', 'last_name': 'Lovelace', 'sex': 'Female', 'date_of_birth': '2015-01-01',
            'lin': 'LIN-ADA-001', 'state_of_origin': 'Lagos', 'lga_of_origin': 'Ikeja', 'program': 'Primary (PRY)',
            'current_class': classroom.name,
        })
        student = Student.objects.get(last_name='Lovelace')
        self.assertTrue(student.user.check_password('lovelace'))
        self.assertEqual(student.user.account_profile.role, 'student')

    def test_backfill_accounts_links_existing_student_and_login_routes(self):
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
        )
        self.assertIsNone(student.user)

        call_command('backfill_accounts')

        student.refresh_from_db()
        self.assertIsNotNone(student.user)
        self.assertTrue(student.user.check_password('lovelace'))
        self.assertEqual(student.user.account_profile.role, 'student')
        self.client.logout()
        response = self.client.post(reverse('login'), {'username': student.student_id, 'password': 'lovelace'})
        self.assertRedirects(response, reverse('student_dashboard'))

    def test_cbt_exam_is_limited_to_basic_classes_and_expires_globally(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Basic 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(subject=subject, classroom=classroom, term=term, start_time=timezone.now() - datetime.timedelta(minutes=5), end_time=timezone.now() + datetime.timedelta(minutes=5))
        question = CBTQuestion.objects.create(exam=exam, question_text='2 + 2?', option_a='4', option_b='5', option_c='6', option_d='7', correct_answer='A')
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        user = get_user_model().objects.create_user(username='basic4', password='lovelace')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        self.client.force_login(user)
        response = self.client.get(reverse('cbt_exam', args=[exam.pk]))
        self.assertEqual(response.status_code, 200)
        exam.end_time = timezone.now() - datetime.timedelta(seconds=1)
        exam.save(update_fields=['end_time'])
        attempt = CBTAttempt.objects.get(exam=exam, student=student)
        response = self.client.get(reverse('cbt_exam', args=[exam.pk]))
        self.assertEqual(response.status_code, 302)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'expired')

    def test_live_or_completed_cbt_exam_cannot_be_deleted(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(
            subject=subject,
            classroom=classroom,
            term=term,
            start_time=timezone.now() - datetime.timedelta(minutes=5),
            end_time=timezone.now() + datetime.timedelta(minutes=60),
        )

        response = self.client.post(reverse('cbt_setup'), {'action': 'delete_exam', 'exam_id': exam.pk}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CBTExam.objects.filter(pk=exam.pk).exists())
        self.assertContains(response, 'Action Denied: Cannot delete an exam that is currently live or has already been completed.')

    def test_question_bank_does_not_render_global_all_questions_section(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        CBTExam.objects.create(subject=subject, classroom=classroom, term=term, start_time=timezone.now() + datetime.timedelta(days=1), end_time=timezone.now() + datetime.timedelta(days=2))

        response = self.client.get(reverse('cbt_questions'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'All Questions')

    def test_question_bank_updates_existing_question_instead_of_creating_duplicate(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(
            subject=subject, classroom=classroom, term=term,
            start_time=timezone.now() + datetime.timedelta(days=1),
            end_time=timezone.now() + datetime.timedelta(days=2),
        )
        question = CBTQuestion.objects.create(
            exam=exam, question_text='Old question', option_a='Old A', option_b='Old B',
            option_c='Old C', option_d='Old D', correct_answer='A', order=3,
        )

        response = self.client.post(reverse('cbt_questions'), {
            'exam': exam.pk, 'question_id': question.pk, 'question_text': 'Updated question',
            'option_a': 'New A', 'option_b': 'New B', 'option_c': 'New C', 'option_d': 'New D',
            'correct_answer': 'C',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        question.refresh_from_db()
        self.assertEqual(CBTQuestion.objects.filter(exam=exam).count(), 1)
        self.assertEqual(question.question_text, 'Updated question')
        self.assertEqual(question.correct_answer, 'C')
        self.assertEqual(question.order, 3)

    def test_question_bank_rejects_live_question_update(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(
            subject=subject, classroom=classroom, term=term,
            start_time=timezone.now() - datetime.timedelta(minutes=1),
            end_time=timezone.now() + datetime.timedelta(hours=1),
        )
        question = CBTQuestion.objects.create(
            exam=exam, question_text='Original', option_a='A', option_b='B',
            option_c='C', option_d='D', correct_answer='A', order=1,
        )

        response = self.client.post(reverse('cbt_questions'), {
            'exam': exam.pk, 'question_id': question.pk, 'question_text': 'Changed',
            'option_a': 'A', 'option_b': 'B', 'option_c': 'C', 'option_d': 'D',
            'correct_answer': 'A',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 403)
        self.assertIn('Exam is currently live or completed', response.json()['message'])
        question.refresh_from_db()
        self.assertEqual(question.question_text, 'Original')

    def test_student_dashboard_hides_attempted_exams_from_message_center(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(
            subject=subject, classroom=classroom, term=term,
            start_time=timezone.now() - datetime.timedelta(minutes=5),
            end_time=timezone.now() + datetime.timedelta(hours=1),
        )
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
            current_class=classroom,
        )
        user = get_user_model().objects.create_user(username='dashboard-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        StudentExamSession.objects.create(student=student, exam=exam, is_completed=True, score=1)

        self.client.force_login(user)
        response = self.client.get(reverse('student_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Class:</span> Primary 4')
        self.assertNotContains(response, '{{ student_class.name }}')
        self.assertContains(response, 'LIN-***-LOCKED')
        self.assertContains(response, 'Access Restricted: Please contact the Proprietor to unlock and view this Learner Identification Number.')
        self.assertContains(response, 'Priority Message Center')
        self.assertContains(response, 'No priority messages are available.')
        self.assertNotContains(response, 'Mathematics CBT Assessment Available')
        self.assertNotContains(response, 'Start Exam')

    def test_lin_access_management_searches_and_updates_visibility(self):
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', lin='LIN-ADA-001')
        Student.objects.create(first_name='Grace', last_name='Hopper', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', lin='LIN-GRACE-001')

        response = self.client.get(reverse('lin_access_management'), {'q': 'Lovelace'})

        self.assertContains(response, 'Ada')
        self.assertNotContains(response, 'Grace')
        response = self.client.post(reverse('lin_access_management'), {'student_id': student.pk, 'is_lin_visible': '1'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        student.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True, 'is_lin_visible': True})
        self.assertTrue(student.is_lin_visible)

    def test_student_dashboard_priority_message_center_uses_instructions_view_link_for_open_exam(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(
            subject=subject, classroom=classroom, term=term,
            start_time=timezone.now() - datetime.timedelta(minutes=5),
            end_time=timezone.now() + datetime.timedelta(hours=1),
        )
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
            current_class=classroom,
        )
        user = get_user_model().objects.create_user(username='message-center-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')

        self.client.force_login(user)
        response = self.client.get(reverse('student_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Priority Message Center')
        self.assertContains(response, 'View')
        self.assertContains(response, reverse('cbt_instructions', args=[exam.pk]))
        self.assertNotContains(response, 'Start Exam')

    def test_student_dashboard_shows_promoted_notice_and_report_card_link(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='Third Term')
        classroom = ClassRoom.objects.create(name='Primary 6', section='Primary', level_number=6)
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom,
        )
        user = get_user_model().objects.create_user(username='promoted-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        record = StudentTermRecord.objects.create(student=student, term=term, promotion_status='Promoted')

        self.client.force_login(user)
        response = self.client.get(reverse('student_dashboard'))

        self.assertContains(response, 'Notice: You have been promoted to Primary 6.')
        self.assertContains(response, reverse('dismiss_promotion_notice'))

        response = self.client.get(reverse('dismiss_promotion_notice'), follow=True)

        record.refresh_from_db()
        self.assertTrue(record.promotion_notice_dismissed)
        self.assertRedirects(response, reverse('student_report_hub'))
        response = self.client.get(reverse('student_dashboard'))
        self.assertNotContains(response, 'Notice: You have been promoted to Primary 6.')

    def test_student_report_hub_shows_unpublished_empty_and_available_states(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        user = get_user_model().objects.create_user(username='report-hub-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        self.client.force_login(user)

        response = self.client.get(reverse('student_report_hub'), {'session': session.pk, 'term': term.pk})
        self.assertContains(response, 'This report card has not been published yet.')

        term.reports_published = True
        term.save(update_fields=['reports_published'])
        response = self.client.get(reverse('student_report_hub'), {'session': session.pk, 'term': term.pk})
        self.assertContains(response, 'No academic records were found for Ada in this term.')

        SubjectResult.objects.create(student=student, term=term, subject=Subject.objects.create(name='Mathematics'))
        response = self.client.get(reverse('student_report_hub'), {'session': session.pk, 'term': term.pk})
        self.assertContains(response, 'View Report Card')

        term.reports_published = False
        term.save(update_fields=['reports_published'])
        response = self.client.get(reverse('student_report_hub'), {'session': session.pk, 'term': term.pk})
        self.assertContains(response, 'This report card has not been published yet.')

    def test_student_report_hub_blocks_results_when_prior_term_fees_are_outstanding(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        first_term = AcademicTerm.objects.create(session=session, term_name='First Term')
        third_term = AcademicTerm.objects.create(session=session, term_name='Third Term', is_active=True, reports_published=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        user = get_user_model().objects.create_user(username='debt-report-hub-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        StudentFeeAccount.objects.create(student=student, term=first_term, session=session, total_billed=5000, amount_paid=2000)
        SubjectResult.objects.create(student=student, term=third_term, subject=Subject.objects.create(name='Mathematics'))
        self.client.force_login(user)

        response = self.client.get(reverse('student_report_hub'), {'session': session.pk, 'term': third_term.pk})

        self.assertContains(response, 'outstanding balance of ₦3,000.00')
        self.assertNotContains(response, 'View Report Card')

        response = self.client.get(reverse('report_card', args=[student.pk]), {'session': session.pk, 'term': third_term.pk})

        self.assertTemplateUsed(response, 'portal/report_locked.html')
        self.assertContains(response, '₦3,000.00')

    def test_parent_report_hub_blocks_child_results_when_prior_term_fees_are_outstanding(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        first_term = AcademicTerm.objects.create(session=session, term_name='First Term')
        third_term = AcademicTerm.objects.create(session=session, term_name='Third Term', is_active=True, reports_published=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        parent = Parent.objects.create(first_name='Grace', last_name='Lovelace', phone_number='08000000000', sex='Female', marital_status='Married', address='Address', state='Lagos', lga='Ikeja')
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, parent=parent)
        user = get_user_model().objects.create_user(username='debt-report-hub-parent', password='pass')
        parent.user = user
        parent.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='parent')
        StudentFeeAccount.objects.create(student=student, term=first_term, session=session, total_billed=5000, amount_paid=2000)
        SubjectResult.objects.create(student=student, term=third_term, subject=Subject.objects.create(name='Mathematics'))
        self.client.force_login(user)

        response = self.client.get(reverse('student_report_hub'), {'session': session.pk, 'term': third_term.pk})

        self.assertContains(response, 'outstanding balance of ₦3,000.00')
        self.assertNotContains(response, 'View Report Card')

        response = self.client.get(reverse('report_card', args=[student.pk]), {'session': session.pk, 'term': third_term.pk})

        self.assertTemplateUsed(response, 'portal/report_locked.html')
        self.assertContains(response, '₦3,000.00')

    def test_parent_dashboard_shows_cumulative_prior_term_balance(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        first_term = AcademicTerm.objects.create(session=session, term_name='First Term')
        active_term = AcademicTerm.objects.create(session=session, term_name='Second Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        parent = Parent.objects.create(first_name='Grace', last_name='Lovelace', phone_number='08000000000', sex='Female', marital_status='Married', address='Address', state='Lagos', lga='Ikeja')
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom, parent=parent)
        user = get_user_model().objects.create_user(username='parent-dashboard-debt', password='pass')
        parent.user = user
        parent.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='parent')
        StudentFeeAccount.objects.create(student=student, term=first_term, session=session, total_billed=5000, amount_paid=2000)
        StudentFeeAccount.objects.create(student=student, term=active_term, session=session, total_billed=7000, amount_paid=7000)
        self.client.force_login(user)

        response = self.client.get(reverse('parent_dashboard'))

        self.assertContains(response, 'Total Outstanding Balance')
        self.assertContains(response, '₦3,000.00')
        self.assertNotContains(response, 'Not billed')

    def test_bursary_payment_clears_previous_term_before_current_term(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        first_term = AcademicTerm.objects.create(session=session, term_name='First Term')
        second_term = AcademicTerm.objects.create(session=session, term_name='Second Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        previous_account = StudentFeeAccount.objects.create(student=student, term=first_term, session=session, total_billed=5000)
        current_account = StudentFeeAccount.objects.create(student=student, term=second_term, session=session, total_billed=7000)

        response = self.client.post(reverse('bursary_dashboard'), {
            'action': 'record_payment', 'account_id': current_account.pk, 'amount_paid': '6000',
        }, follow=True)

        previous_account.refresh_from_db()
        current_account.refresh_from_db()
        self.assertEqual(previous_account.amount_paid, 5000)
        self.assertTrue(previous_account.is_cleared)
        self.assertEqual(current_account.amount_paid, 1000)
        self.assertFalse(current_account.is_cleared)
        self.assertContains(response, 'oldest outstanding term balances first')

        response = self.client.post(reverse('bursary_dashboard'), {
            'action': 'toggle_clearance', 'account_id': current_account.pk, 'is_cleared': '1',
        }, follow=True)

        current_account.refresh_from_db()
        self.assertFalse(current_account.is_cleared)
        self.assertContains(response, 'Clear all previous and current term balances')

    def test_bursary_dashboard_filters_accounts_by_selected_historical_term(self):
        historical_session = AcademicSession.objects.create(name='2025/2026')
        historical_term = AcademicTerm.objects.create(session=historical_session, term_name='Third Term')
        active_session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        active_term = AcademicTerm.objects.create(session=active_session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        historical_account = StudentFeeAccount.objects.create(student=student, term=historical_term, session=historical_session, total_billed=5000)
        StudentFeeAccount.objects.create(student=student, term=active_term, session=active_session, total_billed=7000)

        response = self.client.get(reverse('bursary_dashboard'), {
            'session': historical_session.pk,
            'term': historical_term.pk,
            'classroom': classroom.pk,
        })

        self.assertEqual(response.context['selected_session_obj'], historical_session)
        self.assertEqual(response.context['selected_term_obj'], historical_term)
        self.assertEqual(response.context['accounts'], [historical_account])

    def test_bursary_dashboard_provisions_missing_account_for_historical_enrollment(self):
        historical_session = AcademicSession.objects.create(name='2025/2026')
        historical_term = AcademicTerm.objects.create(session=historical_session, term_name='Third Term')
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        TermEnrollment.objects.create(student=student, term=historical_term, classroom=classroom)
        FeeStructure.objects.create(classroom=classroom, term=historical_term, session=historical_session, amount_required=7500)

        response = self.client.get(reverse('bursary_dashboard'), {
            'session': historical_session.pk,
            'term': historical_term.pk,
            'classroom': classroom.pk,
        })

        account = StudentFeeAccount.objects.get(student=student, term=historical_term, session=historical_session)
        self.assertEqual(account.total_billed, 7500)
        self.assertEqual(response.context['accounts'], [account])

    def test_student_report_hub_prompts_when_no_report_period_is_selected(self):
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)')
        user = get_user_model().objects.create_user(username='empty-report-hub-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')
        self.client.force_login(user)

        response = self.client.get(reverse('student_report_hub'))

        self.assertContains(response, 'Please select an academic session and term above to view results.')

    def test_student_cbt_instructions_screen_links_to_secure_exam_start(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(
            subject=subject, classroom=classroom, term=term,
            start_time=timezone.now() - datetime.timedelta(minutes=5),
            end_time=timezone.now() + datetime.timedelta(hours=1),
        )
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
            current_class=classroom,
        )
        user = get_user_model().objects.create_user(username='instructions-student', password='pass')
        student.user = user
        student.save(update_fields=['user'])
        AccountProfile.objects.create(user=user, role='student')

        self.client.force_login(user)
        response = self.client.get(reverse('cbt_instructions', args=[exam.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Start Now')
        self.assertContains(response, reverse('cbt_exam', args=[exam.pk]))

    def test_cbt_results_page_targets_primary_and_basic_4_and_6_only(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        primary_4 = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        primary_6 = ClassRoom.objects.create(name='Primary 6', section='Primary', level_number=6)
        basic_4 = ClassRoom.objects.create(name='Basic 4', section='Primary', level_number=4)
        other_class = ClassRoom.objects.create(name='Primary 5', section='Primary', level_number=5)
        mathematics = Subject.objects.create(name='Mathematics')
        verbal = Subject.objects.create(name='Verbal Reasoning')
        response = self.client.get(reverse('cbt_results'), {'session': session.pk, 'term': term.pk, 'classroom': primary_4.pk, 'subject': mathematics.name})

        self.assertEqual(response.status_code, 200)
        self.assertIn(primary_4, response.context['classrooms'])
        self.assertIn(primary_6, response.context['classrooms'])
        self.assertIn(basic_4, response.context['classrooms'])
        self.assertNotIn(other_class, response.context['classrooms'])
        self.assertNotIn(verbal, response.context['subjects'])

    def test_cbt_results_filters_accept_numeric_ids_and_text_names(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        primary_4 = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        mathematics = Subject.objects.create(name='Mathematics')
        CBTExam.objects.create(subject=mathematics, classroom=primary_4, term=term, start_time=timezone.now(), end_time=timezone.now() + datetime.timedelta(hours=1))

        id_response = self.client.get(reverse('cbt_results'), {
            'session': str(session.pk),
            'term': str(term.pk),
            'classroom': str(primary_4.pk),
            'subject': mathematics.name,
        })
        text_response = self.client.get(reverse('cbt_results'), {
            'session': session.name,
            'term': term.term_name,
            'classroom': primary_4.name,
            'subject': mathematics.name,
        })

        self.assertEqual(id_response.status_code, 200)
        self.assertEqual(text_response.status_code, 200)
        self.assertIsNotNone(id_response.context['selected_exam'])
        self.assertIsNotNone(text_response.context['selected_exam'])

    def test_delete_submission_clears_cbt_attempt_and_score(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(subject=subject, classroom=classroom, term=term, start_time=timezone.now(), end_time=timezone.now() + datetime.timedelta(hours=1))
        question = CBTQuestion.objects.create(exam=exam, question_text='2 + 2?', option_a='4', option_b='5', option_c='6', option_d='7', correct_answer='A', order=1)
        student = Student.objects.create(first_name='Test', last_name='Student', sex='Male', date_of_birth='2014-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        session_record = StudentExamSession.objects.create(student=student, exam=exam, is_completed=True, score=1, responses={str(question.pk): 'A'})
        attempt = CBTAttempt.objects.create(exam=exam, student=student, status='submitted', score=1, submitted_at=timezone.now())
        CBTResponse.objects.create(attempt=attempt, question=question, answer='A')

        response = self.client.post(reverse('cbt_results'), {'action': 'delete_submission', 'session_id': session_record.pk}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentExamSession.objects.filter(pk=session_record.pk).exists())
        self.assertFalse(CBTAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertFalse(CBTResponse.objects.filter(attempt=attempt).exists())

    def test_student_exam_session_records_submission_time(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        subject = Subject.objects.create(name='Mathematics')
        exam = CBTExam.objects.create(subject=subject, classroom=classroom, term=term, start_time=timezone.now(), end_time=timezone.now() + datetime.timedelta(hours=1))
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom)
        exam_session = StudentExamSession.objects.create(student=student, exam=exam, is_completed=True, score=1)
        exam_session.submitted_at = timezone.now()
        exam_session.save(update_fields=['submitted_at'])

        exam_session.refresh_from_db()
        self.assertIsNotNone(exam_session.submitted_at)

    def test_subject_result_calculates_exam_and_grand_total(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        subject = Subject.objects.create(name='English')
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)')
        result = SubjectResult.objects.create(student=student, term=term, subject=subject, continuous_assessment=25, cbt_obj=24, theory=35)
        self.assertEqual(result.exam_total, 59)
        self.assertEqual(result.total, 84)

    def test_dashboard_exposes_total_parents_and_attendance_metrics(self):
        Parent.objects.create(
            name='A Parent', phone_number='08000000000', sex='Female', marital_status='Married',
            address='Address', state='Lagos', lga='Ikeja',
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Parents')
        self.assertContains(response, 'Daily attendance')

    def test_admin_subpages_have_explicit_routes(self):
        for route_name, page_title in [
            ('cbt_setup', 'Exam Setup'),
            ('cbt_questions', 'Question Bank'),
            ('results_process', 'Result Processing'),
            ('results_uploads', 'Result Uploads'),
        ]:
            response = self.client.get(reverse(route_name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, page_title)

    def test_class_subjects_crud(self):
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        response = self.client.get(reverse('class_subjects'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Class Subject Directory')

        response = self.client.post(reverse('class_subjects'), {
            'action': 'add_subject', 'classroom': classroom.pk, 'subject_name': 'Mathematics',
        })
        self.assertRedirects(response, reverse('class_subjects'))
        assignment = ClassRoomSubject.objects.get(class_room=classroom)
        self.assertEqual(assignment.subject.name, 'Mathematics')

        self.client.post(reverse('class_subjects'), {
            'action': 'edit_subject', 'subject': assignment.subject.pk, 'subject_name': 'Advanced Mathematics',
        })
        assignment.refresh_from_db()
        self.assertEqual(assignment.subject.name, 'Advanced Mathematics')

        self.client.post(reverse('class_subjects'), {
            'action': 'delete_subject', 'subject': assignment.subject.pk,
        })
        self.assertFalse(ClassRoomSubject.objects.filter(pk=assignment.pk).exists())

    def test_attendance_submission_updates_existing_records(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        week = AcademicWeek.objects.create(term=term, week_number=1, start_date=datetime.date(2026, 9, 7), end_date=datetime.date(2026, 9, 11))
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom,
        )
        attendance_date = week.start_date
        register = AttendanceRegister.objects.create(classroom=classroom, session=session, date=attendance_date)
        Attendance.objects.create(register=register, student=student, classroom=classroom, session=session, date=attendance_date, status='Present')

        response = self.client.post(reverse('attendance'), {
            'action': 'save_attendance', 'classroom': classroom.pk, 'week': week.pk, 'day': 0,
            f'status_{student.pk}': 'Absent',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Attendance.objects.filter(student=student, date=attendance_date).count(), 1)
        self.assertEqual(Attendance.objects.get(student=student, date=attendance_date).status, 'Absent')

    def test_clear_attendance_removes_register_and_entries(self):
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        week = AcademicWeek.objects.create(term=term, week_number=1, start_date=datetime.date(2026, 9, 7), end_date=datetime.date(2026, 9, 11))
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=classroom,
        )
        Attendance.objects.create(
            register=AttendanceRegister.objects.create(classroom=classroom, session=session, date=week.start_date),
            student=student, classroom=classroom, session=session, date=week.start_date, status='Present',
        )

        response = self.client.post(reverse('clear_attendance'), {
            'classroom': classroom.pk, 'date': week.start_date.isoformat(), 'week': week.pk, 'day': 0,
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Attendance.objects.filter(classroom=classroom, date=week.start_date).exists())
        self.assertFalse(AttendanceRegister.objects.filter(classroom=classroom, date=week.start_date).exists())

    def test_parent_profile_update_and_student_status_sync(self):
        parent = Parent.objects.create(
            first_name='Grace', last_name='Lovelace', phone_number='08000000000', sex='Female',
            marital_status='Married', address='Address', state='Lagos', lga='Ikeja',
        )
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', parent=parent,
        )

        self.client.post(reverse('parent_profile', args=[parent.pk]), {
            'action': 'update_parent', 'first_name': 'Grace', 'last_name': 'Byron', 'middle_name': '',
            'phone_number': '08111111111', 'sex': 'Female', 'marital_status': 'Married',
            'address': 'Updated address', 'state': 'Lagos', 'lga': 'Ikeja',
        })
        parent.refresh_from_db()
        self.assertEqual(parent.last_name, 'Byron')
        self.assertEqual(parent.address, 'Updated address')
        self.assertEqual(parent.status, 'Active')

        self.client.post(reverse('student_profile', args=[student.pk]), {'action': 'update_status', 'status': 'Graduated'})
        parent.refresh_from_db()
        self.assertEqual(parent.status, 'Active')

    def test_parent_profile_renders_and_links_child(self):
        parent = Parent.objects.create(
            first_name='Grace', last_name='Lovelace', phone_number='08000000000', sex='Female',
            marital_status='Married', address='Address', state='Lagos', lga='Ikeja',
        )
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
        )

        response = self.client.get(reverse('parent_profile', args=[parent.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Parent Details')
        self.assertContains(response, 'Linked Children')

        self.client.post(reverse('parent_profile', args=[parent.pk]), {'action': 'link_student', 'student': student.pk})
        student.refresh_from_db()
        self.assertEqual(student.parent, parent)

    def test_parent_profile_edit_keeps_status_backend_controlled(self):
        parent = Parent.objects.create(
            first_name='Grace', last_name='Lovelace', phone_number='08000000000', sex='Female',
            marital_status='Married', address='Address', state='Lagos', lga='Ikeja', status='Inactive',
        )
        student = Student.objects.create(
            first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01',
            state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)',
        )

        response = self.client.post(reverse('parent_profile', args=[parent.pk]), {
            'action': 'link_student', 'student': student.pk,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertEqual(parent.status, 'Active')

        response = self.client.post(reverse('parent_profile', args=[parent.pk]), {
            'action': 'update_parent', 'first_name': 'Grace', 'last_name': 'Lovelace',
            'middle_name': '', 'phone_number': '08000000000', 'sex': 'Female',
            'email': '', 'religion': '', 'occupation': '', 'marital_status': 'Married',
            'address': 'Updated address', 'state': 'Lagos', 'lga': 'Ikeja',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertEqual(parent.status, 'Active')
        self.assertEqual(parent.address, 'Updated address')

    def test_duplicate_week_generation_shows_error_message(self):
        session = AcademicSession.objects.create(name='2027/2028', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        monday = datetime.date(2027, 9, 6)
        AcademicWeek.objects.create(term=term, week_number=1, start_date=monday, end_date=monday + datetime.timedelta(days=4))

        response = self.client.post(
            reverse('academic_calendar'),
            {'action': 'generate_weeks', 'term': term.pk, 'start_date': monday.isoformat()},
            follow=True,
        )

        self.assertContains(response, 'The 15 weeks have already been generated for this term.')

    def test_delete_weeks_removes_only_selected_term_weeks(self):
        session = AcademicSession.objects.create(name='2027/2028', is_active=True)
        selected_term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        other_term = AcademicTerm.objects.create(session=session, term_name='Second Term', is_active=False)
        monday = datetime.date(2027, 9, 6)
        AcademicWeek.objects.create(term=selected_term, week_number=1, start_date=monday, end_date=monday + datetime.timedelta(days=4))
        AcademicWeek.objects.create(term=other_term, week_number=1, start_date=monday, end_date=monday + datetime.timedelta(days=4))

        response = self.client.post(
            reverse('academic_calendar'),
            {'action': 'delete_weeks', 'term': selected_term.pk},
            follow=True,
        )

        self.assertContains(response, '1 generated academic weeks deleted successfully.')
        self.assertFalse(AcademicWeek.objects.filter(term=selected_term).exists())
        self.assertTrue(AcademicWeek.objects.filter(term=other_term).exists())

    def test_week_generation_requires_term_and_start_date(self):
        response = self.client.post(
            reverse('academic_calendar'),
            {'action': 'generate_weeks'},
            follow=True,
        )

        self.assertContains(response, 'Please select both an active term and a starting date.')

    def test_attendance_none_ids_render_without_crashing(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)

        response = self.client.get(
            reverse('attendance'),
            {'classroom': 'None', 'week': 'None', 'day': 'None'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please select a valid classroom.')

    def test_attendance_weekday_options_use_week_start_date(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='First Term', is_active=True)
        week = AcademicWeek.objects.create(
            term=term,
            week_number=1,
            start_date=datetime.date(2026, 8, 24),
            end_date=datetime.date(2026, 8, 28),
        )
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)

        response = self.client.get(
            reverse('attendance'),
            {'classroom': classroom.pk, 'week': week.pk, 'day': '2'},
        )

        self.assertContains(response, 'Wednesday (26 Aug 2026)')

    def test_duplicate_term_creation_shows_error_message(self):
        session = AcademicSession.objects.create(name='2028/2029', is_active=True)
        AcademicTerm.objects.create(session=session, term_name='Second Term', is_active=False)

        response = self.client.post(
            reverse('academic_calendar'),
            {'action': 'create_term', 'session': session.pk, 'term_name': 'Second Term'},
            follow=True,
        )

        self.assertContains(response, 'This academic term already exists.')

    def test_duplicate_student_creation_shows_error_message(self):
        self.client.post(
            reverse('students'),
            {
                'first_name': 'Ada',
                'last_name': 'Lovelace',
                'sex': 'Female',
                'date_of_birth': '1998-12-10',
                'lin': 'LIN-ADA-002',
                'state_of_origin': 'Lagos',
                'lga_of_origin': 'Eti-Osa',
                'program': 'Primary (PRY)',
                'current_class': '',
                'phone_number': '08000000000',
                'religion': 'Christianity',
                'email': 'ada@example.com',
                'physically_challenged': '',
            },
            follow=True,
        )

        response = self.client.post(
            reverse('students'),
            {
                'first_name': 'Ada',
                'last_name': 'Lovelace',
                'sex': 'Female',
                'date_of_birth': '1998-12-10',
                'lin': 'LIN-ADA-003',
                'state_of_origin': 'Lagos',
                'lga_of_origin': 'Eti-Osa',
                'program': 'Primary (PRY)',
                'current_class': '',
                'phone_number': '08000000001',
                'religion': 'Christianity',
                'email': 'ada2@example.com',
                'physically_challenged': '',
            },
            follow=True,
        )

        self.assertContains(response, 'A student with this profile already exists.')

    def test_duplicate_teacher_creation_shows_error_message(self):
        self.client.post(
            reverse('teachers'),
            {
                'first_name': 'Grace',
                'last_name': 'Hopper',
                'other_name': '',
                'staff_type': 'Teaching',
                'birth_month': '12',
                'birth_day': '9',
                'state_of_origin': 'Kwara',
                'lga_of_origin': 'Ilorin East',
                'phone_number': '08011111111',
                'email': 'grace@example.com',
                'qualification_school': ['School A'],
                'qualification': ['BSc'],
                'qualification_year': ['2020'],
                'qualification_highest': ['1'],
            },
            follow=True,
        )

        response = self.client.post(
            reverse('teachers'),
            {
                'first_name': 'Grace',
                'last_name': 'Hopper',
                'other_name': '',
                'staff_type': 'Teaching',
                'birth_month': '12',
                'birth_day': '9',
                'state_of_origin': 'Kwara',
                'lga_of_origin': 'Ilorin East',
                'phone_number': '08022222222',
                'email': 'grace@example.com',
                'qualification_school': ['School B'],
                'qualification': ['MSc'],
                'qualification_year': ['2024'],
                'qualification_highest': ['1'],
            },
            follow=True,
        )

        self.assertContains(response, 'A teacher with this email already exists.')

    def test_manage_classes_terminal_clears_next_class_and_displays_graduating(self):
        cls_from = ClassRoom.objects.create(name='Primary 5', section='Primary', level_number=5)
        cls_to = ClassRoom.objects.create(name='Primary 6', section='Primary', level_number=6)
        cls_from.next_class = cls_to
        cls_from.save()

        response = self.client.post(reverse('manage_classes'), {
            'classroom_id': cls_from.pk,
            'is_terminal': '1',
            'next_class': str(cls_to.pk),
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        cls_from.refresh_from_db()
        self.assertTrue(cls_from.is_terminal)
        self.assertIsNone(cls_from.next_class)
        self.assertContains(response, 'Graduating (Terminal)')

    def test_session_rollover_readiness_strictly_checks_all_classrooms(self):
        c1 = ClassRoom.objects.create(name='Basic 1', section='Primary', level_number=1)
        c2 = ClassRoom.objects.create(name='Basic 2', section='Primary', level_number=2, is_terminal=True)
        c1.next_class = c2
        c1.save()

        response = self.client.get(reverse('session_rollover'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['all_configured'])

        c3 = ClassRoom.objects.create(name='Basic 3', section='Primary', level_number=3)
        response = self.client.get(reverse('session_rollover'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['all_configured'])

    def test_session_rollover_counts_and_button_enable_state(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        term = AcademicTerm.objects.create(session=session, term_name='Third Term', is_active=True)
        c1 = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1)
        c2 = ClassRoom.objects.create(name='Primary 2', section='Primary', level_number=2, is_terminal=True)
        c1.next_class = c2
        c1.save()

        s1 = Student.objects.create(first_name='A', last_name='One', sex='Male', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=c1, status='Active')
        s2 = Student.objects.create(first_name='B', last_name='Two', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=c2, status='Active')
        s3 = Student.objects.create(first_name='C', last_name='Three', sex='Male', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=c1, status='Active')

        StudentTermRecord.objects.create(student=s1, term=term, promotion_status='Promoted')
        StudentTermRecord.objects.create(student=s2, term=term, promotion_status='Promoted')
        StudentTermRecord.objects.create(student=s3, term=term, promotion_status='Repeated')

        response = self.client.get(reverse('session_rollover'), {'session_id': session.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['promoted_count'], 1)
        self.assertEqual(response.context['graduating_count'], 1)
        self.assertEqual(response.context['repeated_count'], 1)
        self.assertTrue(response.context['all_configured'])
        self.assertNotContains(response, 'disabled class="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600')

    def test_session_rollover_requires_third_term_records(self):
        session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        classroom = ClassRoom.objects.create(name='Primary 1', section='Primary', level_number=1, is_terminal=True)

        response = self.client.get(reverse('session_rollover'), {'session_id': session.pk})

        self.assertFalse(response.context['has_third_term_records'])
        self.assertContains(response, 'Session rollover is only available at the end of the Third Term.')
        self.assertContains(response, 'disabled class="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600')

        response = self.client.post(
            reverse('session_rollover'),
            {'action': 'execute_rollover', 'session_id': session.pk},
            follow=True,
        )

        session.refresh_from_db()
        self.assertFalse(session.rollover_completed)
        self.assertContains(response, 'Session rollover is only available at the end of the Third Term.')

    def test_session_rollover_moves_students_and_enrolls_them_in_next_session_first_term(self):
        closing_session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        next_session = AcademicSession.objects.create(name='2027/2028')
        closing_term = AcademicTerm.objects.create(session=closing_session, term_name='Third Term')
        first_term = AcademicTerm.objects.create(session=next_session, term_name='First Term')
        current_class = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        next_class = ClassRoom.objects.create(name='Primary 6', section='Primary', level_number=6)
        current_class.next_class = next_class
        current_class.save()
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=current_class, status='Active')
        StudentTermRecord.objects.create(student=student, term=closing_term, promotion_status='Promoted')

        response = self.client.post(reverse('session_rollover'), {'action': 'execute_rollover', 'session_id': closing_session.pk}, follow=True)

        student.refresh_from_db()
        closing_session.refresh_from_db()
        self.assertRedirects(response, f"{reverse('session_rollover')}?session_id={closing_session.pk}")
        self.assertEqual(student.current_class, next_class)
        self.assertTrue(TermEnrollment.objects.filter(student=student, term=first_term, classroom=student.current_class).exists())
        self.assertTrue(closing_session.rollover_completed)
        self.assertTrue(response.context['is_rolled_over'])
        self.assertContains(response, 'Session rollover executed successfully. Students have been migrated.')
        self.assertContains(response, 'Rollover Completed')
        self.assertContains(response, 'Revert Rollover (Reset)')

        response = self.client.post(reverse('session_rollover'), {'action': 'revert_rollover', 'session_id': closing_session.pk}, follow=True)

        student.refresh_from_db()
        closing_session.refresh_from_db()
        self.assertRedirects(response, f"{reverse('session_rollover')}?session_id={closing_session.pk}")
        self.assertEqual(student.current_class, current_class)
        self.assertEqual(student.status, 'Active')
        self.assertFalse(TermEnrollment.objects.filter(student=student, term=first_term).exists())
        self.assertFalse(closing_session.rollover_completed)
        self.assertFalse(response.context['is_rolled_over'])
        self.assertContains(response, 'Rollover successfully reverted for testing.')

    def test_session_rollover_updates_an_existing_first_term_enrollment(self):
        closing_session = AcademicSession.objects.create(name='2026/2027', is_active=True)
        next_session = AcademicSession.objects.create(name='2027/2028')
        closing_term = AcademicTerm.objects.create(session=closing_session, term_name='Third Term')
        first_term = AcademicTerm.objects.create(session=next_session, term_name='First Term')
        current_class = ClassRoom.objects.create(name='Primary 4', section='Primary', level_number=4)
        next_class = ClassRoom.objects.create(name='Primary 6', section='Primary', level_number=6)
        current_class.next_class = next_class
        current_class.save()
        student = Student.objects.create(first_name='Ada', last_name='Lovelace', sex='Female', date_of_birth='2015-01-01', state_of_origin='Lagos', lga_of_origin='Ikeja', program='Primary (PRY)', current_class=current_class, status='Active')
        StudentTermRecord.objects.create(student=student, term=closing_term, promotion_status='Promoted')
        enrollment = TermEnrollment.objects.create(student=student, term=first_term, classroom=current_class)

        self.client.post(reverse('session_rollover'), {'action': 'execute_rollover', 'session_id': closing_session.pk})

        student.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.classroom, student.current_class)

        self.client.post(reverse('session_rollover'), {'action': 'revert_rollover', 'session_id': closing_session.pk})

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.classroom, current_class)



from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.conf import settings
import re
import secrets

class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class ClassRoom(models.Model):
    SECTION_CHOICES = [
        ('KG', 'Kindergarten'),
        ('Nursery', 'Nursery'),
        ('Primary', 'Primary'),
    ]

    name = models.CharField(max_length=50, unique=True)  # e.g., "Primary 4", "KG 2"
    section = models.CharField(max_length=100, choices=SECTION_CHOICES)
    level_number = models.IntegerField(null=True, blank=True) # e.g., 1, 2, 3, 4, 6 (skipping 5)
    sequence = models.IntegerField(null=True, blank=True)
    is_terminal = models.BooleanField(default=False)
    next_class = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='previous_classes')
    
    # Class Teacher (Homeroom Teacher) allocation linked to your Teacher model
    class_teacher = models.ForeignKey('Teacher', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_class')

    def __str__(self):
        return f"{self.name} ({self.section})"

class ClassRoomSubject(models.Model):
    class_room = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name='class_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.class_room.name} -> {self.subject.name}"


class AccountProfile(models.Model):
    ROLE_CHOICES = [('admin', 'Admin'), ('principal', 'Principal'), ('bursar', 'Bursar'), ('teacher', 'Teacher'), ('registrar', 'Registrar'), ('parent', 'Parent'), ('student', 'Student')]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='account_profile')
    role = models.CharField(max_length=100, choices=ROLE_CHOICES)
    profile_picture = models.ImageField(upload_to='account_profiles/', max_length=255, blank=True, null=True)

    def __str__(self):
        return f'{self.user.username} ({self.role})'


# --- Your Exact Student Model (Untouched) ---
class Student(models.Model):
    SEX_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
    ]

    PROGRAM_CHOICES = [
        ('Kindergarten (KG)', 'Kindergarten (KG)'),
        ('Nursery (NUR)', 'Nursery (NUR)'),
        ('Primary (PRY)', 'Primary (PRY)'),
    ]

    RELIGION_CHOICES = [
        ('Christianity', 'Christianity'),
        ('Islam', 'Islam'),
        ('Other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Student', 'Student'),
        ('Transferred', 'Transferred'),
        ('Expelled', 'Expelled'),
        ('Graduated', 'Graduated'),
    ]

    # Auto-Generated ID
    student_id = models.CharField(max_length=100, unique=True, blank=True)
    lin = models.CharField(max_length=50, unique=True, blank=True, null=True)
    is_lin_visible = models.BooleanField(default=False)

    # Required Bio Data
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50, verbose_name='Surname')
    other_name = models.CharField(max_length=50, blank=True, null=True)
    sex = models.CharField(max_length=100, choices=SEX_CHOICES)
    date_of_birth = models.DateField()
    state_of_origin = models.CharField(max_length=50)
    lga_of_origin = models.CharField(max_length=50)

    # Academic Structure
    program = models.CharField(max_length=50, choices=PROGRAM_CHOICES)
    current_class = models.ForeignKey('ClassRoom', on_delete=models.SET_NULL, null=True, blank=True, related_name='students')

    # Media & Special Status
    passport = models.ImageField(upload_to='student_passports/', max_length=255, blank=True, null=True)
    physically_challenged = models.BooleanField(default=False)

    # Optional Contact & Personal Info
    phone_number = models.CharField(max_length=100, blank=True, null=True)
    religion = models.CharField(max_length=100, choices=RELIGION_CHOICES, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Student')
    date_enrolled = models.DateField(auto_now_add=True)
    consecutive_absence_flag = models.BooleanField(default=False)
    teacher_comment = models.TextField(blank=True, default='')
    parent = models.ForeignKey('Parent', on_delete=models.SET_NULL, null=True, blank=True, related_name='children')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_record')

    def save(self, *args, **kwargs):
        if not self.student_id:
            current_year = timezone.now().year
            
            if 'Kindergarten' in self.program:
                prog_code = 'KG'
            elif 'Nursery' in self.program:
                prog_code = 'NUR'
            else:
                prog_code = 'PRY'
            
            prefix = f"FLA/{current_year}/{prog_code}/"
            sequence_numbers = [
                int(value[len(prefix):])
                for value in Student.objects.filter(student_id__startswith=prefix).values_list('student_id', flat=True)
                if value[len(prefix):].isdigit()
            ]
            self.student_id = f"{prefix}{max(sequence_numbers, default=0) + 1:03d}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student_id} - {self.last_name} {self.first_name}"

    @property
    def has_portal_access(self):
        classroom = self.current_class
        if not classroom:
            return False
        if classroom.section == 'Primary' and (classroom.level_number or 0) >= 4:
            return True
        class_name = classroom.name.lower()
        return any(label in class_name for label in ('primary 4', 'primary 5', 'primary 6', 'basic 4', 'basic 5', 'basic 6'))


class Parent(models.Model):
    SEX_CHOICES = [('Male', 'Male'), ('Female', 'Female')]
    MARITAL_STATUS_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Separated', 'Separated'),
        ('Divorced', 'Divorced'),
        ('Widowed', 'Widowed'),
    ]

    parent_id = models.CharField(max_length=100, unique=True, blank=True)
    name = models.CharField(max_length=120, blank=True)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    middle_name = models.CharField(max_length=50, blank=True)
    phone_number = models.CharField(max_length=100, unique=True)
    sex = models.CharField(max_length=100, choices=SEX_CHOICES)
    email = models.EmailField(blank=True, null=True)
    religion = models.CharField(max_length=100, blank=True, null=True)
    occupation = models.CharField(max_length=100, blank=True, null=True)
    marital_status = models.CharField(max_length=100, choices=MARITAL_STATUS_CHOICES)
    address = models.TextField()
    state = models.CharField(max_length=50)
    lga = models.CharField(max_length=80)
    status = models.CharField(max_length=100, choices=[('Active', 'Active'), ('Inactive', 'Inactive')], default='Inactive')
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='parent_record')

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.parent_id:
            year = timezone.now().year
            prefix = f'FLA/PAR/{year}/'
            sequence_numbers = [
                int(value[len(prefix):])
                for value in Parent.objects.filter(parent_id__startswith=prefix).values_list('parent_id', flat=True)
                if value[len(prefix):].isdigit()
            ]
            self.parent_id = f'{prefix}{max(sequence_numbers, default=0) + 1:03d}'
        structured_name = ' '.join(part for part in [self.first_name, self.middle_name, self.last_name] if part).strip()
        if structured_name:
            self.name = structured_name
        super().save(*args, **kwargs)

    def __str__(self):
        return ' '.join(part for part in [self.first_name, self.middle_name, self.last_name] if part).strip() or self.name

    @property
    def display_name(self):
        return str(self)


class Teacher(models.Model):
    staff_id = models.CharField(max_length=100, unique=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50, verbose_name='Surname')
    other_name = models.CharField(max_length=50, blank=True)
    other_name = models.CharField(max_length=50, blank=True, null=True)
    
    staff_type = models.CharField(max_length=50, blank=True, null=True)
    birth_month = models.CharField(max_length=100, blank=True, null=True)
    birth_day = models.CharField(max_length=100, blank=True, null=True)
    state_of_origin = models.CharField(max_length=50, blank=True, null=True)
    lga_of_origin = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=100, default='Active') # Active or Inactive
    
    phone_number = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    passport = models.ImageField(upload_to='teacher_passports/', max_length=255, blank=True, null=True)
    date_joined = models.DateField(auto_now_add=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='teacher_record')

    def save(self, *args, **kwargs):
        if not self.staff_id:
            current_year = timezone.now().year
            count = Teacher.objects.count() + 1
            self.staff_id = f"FLA/{current_year}/STF/{count:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff_id} - {self.last_name} {self.first_name}"


class TeacherQualification(models.Model):
    QUALIFICATION_CHOICES = [
        ('Below SSCE', 'Below SSCE'),
        ('SSCE/WASSCE', 'SSCE/WASSCE'),
        ('OND/Diploma', 'OND/Diploma'),
        ('NCE', 'NCE'),
        ('HND', 'HND'),
        ('BSc', 'BSc'),
        ('MSc', 'MSc'),
        ('BA', 'BA'),
        ('MA', 'MA'),
        ('MEd', 'MEd'),
        ('PhD', 'PhD'),
    ]

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='qualifications')
    school = models.CharField(max_length=150)
    qualification = models.CharField(max_length=100, choices=QUALIFICATION_CHOICES)
    year = models.PositiveIntegerField()
    is_highest = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_highest', '-year', 'id']

    def __str__(self):
        return f"{self.teacher} - {self.qualification} ({self.year})"


class AcademicSession(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=False)
    rollover_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_active:
            AcademicSession.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


class AcademicTerm(models.Model):
    TERM_CHOICES = [('First Term', 'First Term'), ('Second Term', 'Second Term'), ('Third Term', 'Third Term')]
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='terms')
    term_name = models.CharField(max_length=100, choices=TERM_CHOICES)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    next_term_begins = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    broadsheet_approved = models.BooleanField(default=False)
    reports_published = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'term_name'], name='unique_session_term')]
        ordering = ['start_date']

    def save(self, *args, **kwargs):
        if self.is_active:
            AcademicTerm.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.term_name


class AcademicWeek(models.Model):
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='weeks')
    week_number = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['term', 'week_number'], name='unique_term_week')]
        ordering = ['week_number']


class Holiday(models.Model):
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='holidays')
    date = models.DateField()
    description = models.CharField(max_length=150)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['term', 'date'], name='unique_term_holiday')]
        ordering = ['date']


class TermEnrollment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='term_enrollments')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='enrollments')
    classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name='term_enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'term'], name='unique_student_term_enrollment')]


class SessionRolloverRecord(models.Model):
    closing_session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name='rollover_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='rollover_records')
    original_class = models.ForeignKey(ClassRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    original_status = models.CharField(max_length=100)
    target_term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='+')
    created_enrollment = models.BooleanField(default=False)
    previous_enrollment_class = models.ForeignKey(ClassRoom, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['closing_session', 'student'], name='unique_session_rollover_student')]


class FeeStructure(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name='fee_structures')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='fee_structures')
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='fee_structures')
    amount_required = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['classroom', 'term', 'session'], name='unique_classroom_term_session_fee_structure')]


class StudentFeeAccount(models.Model):
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='fee_accounts')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='student_fee_accounts')
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='student_fee_accounts')
    total_billed = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_cleared = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'term', 'session'], name='unique_student_term_session_fee_account')]

    @property
    def balance(self):
        return self.total_billed - self.amount_paid

    def save(self, *args, **kwargs):
        if self.balance <= 0:
            self.is_cleared = True
        super().save(*args, **kwargs)


class FeePayment(models.Model):
    account = models.ForeignKey(StudentFeeAccount, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_fee_payments')

    class Meta:
        ordering = ['-paid_at', '-id']


class SchoolPaymentAccount(models.Model):
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=100)
    account_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-is_active', 'bank_name', 'account_name']

    def save(self, *args, **kwargs):
        if self.is_active:
            SchoolPaymentAccount.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.bank_name} - {self.account_name}'


class AttendanceRegister(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name='attendance_registers')
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='attendance_registers')
    date = models.DateField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['classroom', 'session', 'date'], name='unique_classroom_attendance_register'),
        ]
        ordering = ['-date', 'classroom__name']

    def __str__(self):
        return f"{self.classroom.name} - {self.date}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('Present', 'Present'),
        ('Absent', 'Absent'),
        ('Late', 'Late'),
        ('Excused', 'Excused'),
    ]

    register = models.ForeignKey(AttendanceRegister, on_delete=models.CASCADE, related_name='entries')
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name='attendance')
    classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name='attendance')
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='attendance')
    date = models.DateField()
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Present')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'classroom', 'session', 'date'], name='unique_student_attendance'),
        ]
        ordering = ['student__last_name', 'student__first_name']

    def __str__(self):
        return f"{self.student} - {self.date} - {self.status}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = [('Present', 'Present'), ('Absent', 'Absent'), ('Late', 'Late')]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='legacy_attendance_records')
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, null=True, blank=True, related_name='legacy_attendance_records')
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, null=True, blank=True, related_name='legacy_attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Present')
    is_present = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.student.first_name} - {self.date}"


class CBTExam(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='exams')
    classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name='cbt_exams')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='cbt_exams')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    duration = models.IntegerField(help_text='Duration in minutes', default=60)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_time']

    @property
    def question_limit(self):
        return 30 if self.subject.name.lower() in {'mathematics', 'english'} else 20

    def is_eligible_class(self):
        class_name = (self.classroom.name or '').lower()
        return any(term in class_name for term in ('primary 4', 'basic 4', 'primary 6', 'basic 6'))

    def __str__(self):
        return f'{self.classroom.name} - {self.subject.name}'


class CBTQuestion(models.Model):
    ANSWER_CHOICES = [('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]
    exam = models.ForeignKey(CBTExam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    image = models.ImageField(upload_to='cbt_questions/', blank=True, null=True)
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_answer = models.CharField(max_length=100, choices=ANSWER_CHOICES)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['order', 'id']
        constraints = [models.UniqueConstraint(fields=['exam', 'order'], name='unique_exam_question_order')]


class StudentExamSession(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_sessions')
    exam = models.ForeignKey(CBTExam, on_delete=models.CASCADE, related_name='student_sessions')
    start_time = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    score = models.FloatField(null=True, blank=True)
    responses = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'exam'], name='unique_student_exam_session')]


class CBTAttempt(models.Model):
    STATUS_CHOICES = [('in_progress', 'In progress'), ('submitted', 'Submitted'), ('expired', 'Expired')]
    exam = models.ForeignKey(CBTExam, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='cbt_attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='in_progress')
    score = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['exam', 'student'], name='unique_exam_student_attempt')]


class CBTResponse(models.Model):
    attempt = models.ForeignKey(CBTAttempt, on_delete=models.CASCADE, related_name='responses')
    question = models.ForeignKey(CBTQuestion, on_delete=models.CASCADE)
    answer = models.CharField(max_length=100, choices=CBTQuestion.ANSWER_CHOICES, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['attempt', 'question'], name='unique_attempt_question_response')]


class SubjectResult(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='subject_results')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='subject_results')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='results')
    continuous_assessment = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cbt_obj = models.DecimalField(max_digits=5, decimal_places=2, default=0, editable=False)
    theory = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    exam_total = models.DecimalField(max_digits=5, decimal_places=2, default=0, editable=False)
    total = models.DecimalField(max_digits=5, decimal_places=2, default=0, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'term', 'subject'], name='unique_student_term_subject_result')]

    def save(self, *args, **kwargs):
        self.continuous_assessment = min(max(self.continuous_assessment, 0), 30)
        self.cbt_obj = min(max(self.cbt_obj, 0), 30)
        self.theory = min(max(self.theory, 0), 40)
        self.exam_total = self.cbt_obj + self.theory
        self.total = self.continuous_assessment + self.exam_total
        super().save(*args, **kwargs)


class StudentEvaluation(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='evaluations')
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='student_evaluations')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='student_evaluations')
    attentiveness = models.PositiveSmallIntegerField(null=True, blank=True)
    punctuality = models.PositiveSmallIntegerField(null=True, blank=True)
    self_control = models.PositiveSmallIntegerField(null=True, blank=True)
    relationship_with_others = models.PositiveSmallIntegerField(null=True, blank=True)
    music = models.PositiveSmallIntegerField(null=True, blank=True)
    indoor_games = models.PositiveSmallIntegerField(null=True, blank=True)
    outdoor_games = models.PositiveSmallIntegerField(null=True, blank=True)
    club_association = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'session', 'term'], name='unique_student_session_term_evaluation')]


class StudentTermRecord(models.Model):
    PROMOTION_CHOICES = [('Promoted', 'Promoted'), ('Repeated', 'Repeated')]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='term_records')
    term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='student_records')
    term_one_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    term_two_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    term_three_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cumulative_average = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    promotion_status = models.CharField(max_length=100, choices=PROMOTION_CHOICES, default='Repeated')
    promotion_notice_dismissed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student', 'term'], name='unique_student_term_record')]


class AutomatedCommentBank(models.Model):
    min_score = models.FloatField()
    max_score = models.FloatField()
    char_poor = models.TextField(help_text='Comment for character/skills average 0-2')
    char_good = models.TextField(help_text='Comment for character/skills average 3-4')
    char_excellent = models.TextField(help_text='Comment for character/skills average 5')

    class Meta:
        ordering = ['-min_score']

    def __str__(self):
        return f'{self.min_score:.2f} - {self.max_score:.2f}'


class ClassResultStatus(models.Model):
    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name='result_statuses')
    term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='result_statuses')
    is_published = models.BooleanField(default=False)
    scheduled_publish_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['classroom', 'term'], name='unique_classroom_term_result_status')]

    @property
    def is_live(self):
        if self.is_published:
            return True
        return bool(self.scheduled_publish_date and self.scheduled_publish_date <= timezone.now())

    def __str__(self):
        return f'{self.classroom.name} - {self.term}'


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('BROADSHEET_APPROVED', 'Broadsheet approved'),
        ('BROADSHEET_DISAPPROVED', 'Broadsheet disapproved'),
        ('RESULT_PUBLISHED', 'Results published'),
        ('RESULT_UNPUBLISHED', 'Results unpublished'),
        ('SCORE_MODIFIED', 'Scores modified'),
        ('COMMENT_MODIFIED', 'Comment modified'),
        ('DEBT_OVERRIDDEN', 'Debt clearance changed'),
        ('PAYMENT_RECORDED', 'Payment recorded'),
        ('TRUANCY_FLAGGED', 'Truancy flag raised'),
        ('ROLE_CHANGED', 'User role changed'),
        ('PAYROLL_PROCESSED', 'Payroll processed'),
        ('PAYROLL_APPROVED', 'Payroll approved'),
        ('PAYROLL_DISBURSED', 'Payroll disbursed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='audit_logs')
    action_type = models.CharField(max_length=100, choices=ACTION_CHOICES)
    target_description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    changes_json = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', '-pk']

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError('Audit logs are immutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('Audit logs are immutable.')


class AdmissionCampaign(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Closed', 'Closed'),
        ('Archived', 'Archived'),
    ]

    campaign_name = models.CharField(max_length=150)
    target_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='admission_campaigns')
    target_term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='admission_campaigns')
    application_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deadline = models.DateTimeField()
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Active')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-deadline']

    def save(self, *args, **kwargs):
        if self.deadline and self.deadline <= timezone.now():
            self.status = 'Closed'
        self.is_active = self.status == 'Active'
        if self.is_active:
            AdmissionCampaign.objects.exclude(pk=self.pk).filter(status='Active').update(
                status='Closed',
                is_active=False,
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return self.campaign_name


class Applicant(models.Model):
    PAYMENT_STATUS_CHOICES = [('Pending', 'Pending'), ('Verified', 'Verified')]
    ADMISSION_STATUS_CHOICES = [('Pending', 'Pending'), ('Verified', 'Verified'), ('Approved', 'Approved'), ('Accepted', 'Accepted'), ('Rejected', 'Rejected')]
    SCHOOL_TYPE_CHOICES = [('None', 'First School (No Previous School)'), ('Public', 'Public'), ('Private', 'Private')]

    campaign = models.ForeignKey(AdmissionCampaign, on_delete=models.CASCADE, related_name='applicants')
    temp_reg_number = models.CharField(max_length=50, unique=True, blank=True)

    # Step 1: Basic Applicant Data
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50, verbose_name='Surname')
    other_name = models.CharField(max_length=50, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=100, choices=[('Male', 'Male'), ('Female', 'Female')], blank=True)
    nationality = models.CharField(max_length=50, default='Nigerian', blank=True)
    religion = models.CharField(max_length=100, choices=Student.RELIGION_CHOICES, blank=True)
    state_of_origin = models.CharField(max_length=50, blank=True)
    lga = models.CharField(max_length=80, blank=True)
    passport = models.ImageField(upload_to='applicant_passports/', max_length=255, blank=True, null=True)

    # Step 2: Challenges & Academic Background
    has_disability = models.BooleanField(default=False)
    disability_details = models.CharField(max_length=255, blank=True)
    school_type = models.CharField(max_length=50, choices=SCHOOL_TYPE_CHOICES, blank=True)
    previous_school = models.CharField(max_length=150, blank=True)
    present_class = models.CharField(max_length=50, blank=True)
    programme_of_study = models.CharField(max_length=50, choices=Student.PROGRAM_CHOICES, blank=True)
    intended_class = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name='applicants')

    # Step 3: Parent/Guardian Information
    parent_name = models.CharField(max_length=100, blank=True)
    parent_phone = models.CharField(max_length=100, blank=True)
    parent_email = models.EmailField(blank=True, null=True)
    father_name = models.CharField(max_length=100, blank=True)
    father_occupation = models.CharField(max_length=100, blank=True)
    father_job_title = models.CharField(max_length=100, blank=True)
    father_phone = models.CharField(max_length=100, blank=True)
    father_email = models.EmailField(blank=True, null=True)
    father_address = models.TextField(blank=True)
    mother_name = models.CharField(max_length=100, blank=True)
    mother_occupation = models.CharField(max_length=100, blank=True)
    mother_job_title = models.CharField(max_length=100, blank=True)
    mother_phone = models.CharField(max_length=100, blank=True)
    mother_email = models.EmailField(blank=True, null=True)
    mother_address = models.TextField(blank=True)
    next_of_kin_name = models.CharField(max_length=120, blank=True)
    next_of_kin_relationship = models.CharField(max_length=50, blank=True)
    next_of_kin_phone = models.CharField(max_length=100, blank=True)

    payment_status = models.CharField(max_length=100, choices=PAYMENT_STATUS_CHOICES, default='Pending')
    admission_status = models.CharField(max_length=100, choices=ADMISSION_STATUS_CHOICES, default='Pending')
    enrolled_student = models.OneToOneField('Student', on_delete=models.SET_NULL, null=True, blank=True, related_name='applicant_record')
    provisioned_parent = models.OneToOneField('Parent', on_delete=models.SET_NULL, null=True, blank=True, related_name='applicant_parent_record')
    student_id = models.CharField(max_length=100, blank=True)
    parent_id = models.CharField(max_length=100, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def _new_temp_reg_number(self):
        session_name = getattr(self.campaign.target_session, 'name', '')
        session_year = re.search(r'20\d{2}', session_name or '')
        year_code = session_year.group(0)[-2:] if session_year else timezone.now().strftime('%y')
        class_code = re.sub(r'[^A-Z0-9]', '', (self.intended_class.name or '').upper())[:8]
        class_code = class_code or 'CLASS'
        alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
        random_suffix = ''.join(secrets.choice(alphabet) for _ in range(6))
        return f'FLA-{year_code}-{class_code}-{random_suffix}'

    def save(self, *args, **kwargs):
        if self.temp_reg_number:
            super().save(*args, **kwargs)
            return

        while True:
            candidate = self._new_temp_reg_number()
            try:
                with transaction.atomic():
                    if Applicant.objects.filter(temp_reg_number=candidate).exists():
                        continue
                    self.temp_reg_number = candidate
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                self.temp_reg_number = ''

    def __str__(self):
        return f"{self.temp_reg_number} - {self.first_name} {self.last_name}"


class Message(models.Model):
    PRIORITY_CHOICES = [('Standard', 'Standard'), ('Important', 'Important'), ('Urgent', 'Urgent')]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_messages')
    subject = models.CharField(max_length=150)
    body = models.TextField()
    priority = models.CharField(max_length=100, choices=PRIORITY_CHOICES, default='Standard')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return self.subject


class MessageRecipient(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='recipients')
    recipient_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    is_read = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['message', 'recipient_user'], name='unique_message_recipient')]
        ordering = ['-message__timestamp']

    def __str__(self):
        return f"{self.message.subject} -> {self.recipient_user.username}"


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'Notification for {self.recipient.username} - {self.title}'


class StaffSalaryProfile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='salary_profiles')
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name='salary_profiles')
    academic_term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name='salary_profiles')
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    housing_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pension_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['user__username']
        constraints = [
            models.UniqueConstraint(fields=['user', 'academic_session', 'academic_term'], name='unique_staff_salary_profile_per_term'),
        ]

    def clean(self):
        if self.academic_session_id and self.academic_term_id:
            if self.academic_term.session_id != self.academic_session_id:
                raise ValidationError({'academic_term': 'The salary term must belong to the selected academic session.'})

    @property
    def gross_pay(self):
        return self.base_salary + self.allowances

    @property
    def total_deductions(self):
        return self.deductions

    @property
    def net_salary(self):
        return self.base_salary + self.allowances - self.deductions

    @property
    def net_pay(self):
        return self.net_salary

    def __str__(self):
        return f"Salary profile - {self.user.username}"


class PayrollRun(models.Model):
    STATUS_CHOICES = [('Draft', 'Draft'), ('Approved', 'Approved'), ('Disbursed', 'Disbursed')]
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December'),
    ]

    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField()
    academic_session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, null=True, blank=True, related_name='payroll_runs')
    academic_term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, null=True, blank=True, related_name='payroll_runs')
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='processed_payroll_runs')
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='Draft')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['month', 'year'], name='unique_payroll_run_month_year')]
        ordering = ['-year', '-month']

    def __str__(self):
        return f"Payroll {self.month:02d}/{self.year}"


class Payslip(models.Model):
    salary_profile = models.ForeignKey(StaffSalaryProfile, on_delete=models.PROTECT, related_name='payslips')
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name='payslips')
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_disbursed = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['salary_profile', 'payroll_run'], name='unique_payslip_per_run')]
        ordering = ['salary_profile__user__username']

    def __str__(self):
        return f"Payslip - {self.salary_profile.user.username} ({self.payroll_run})"
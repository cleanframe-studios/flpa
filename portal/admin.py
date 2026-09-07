from django.contrib import admin
from .models import Student, Teacher, AttendanceRecord, Parent, Subject, ClassRoom, ClassRoomSubject, CBTExam, CBTQuestion, CBTAttempt, CBTResponse, SubjectResult, AccountProfile, StudentTermRecord, FeeStructure, StudentFeeAccount, FeePayment, SchoolPaymentAccount, AdmissionCampaign, Applicant, Message, MessageRecipient, StaffSalaryProfile, PayrollRun, Payslip

admin.site.register(Student)
admin.site.register(Teacher)
admin.site.register(AttendanceRecord)
admin.site.register(Parent)
admin.site.register(AccountProfile)
admin.site.register(Subject)
admin.site.register(ClassRoom)
admin.site.register(ClassRoomSubject)
admin.site.register(CBTExam)
admin.site.register(CBTQuestion)
@admin.action(description='Reset selected student exam attempts')
def reset_cbt_attempts(modeladmin, request, queryset):
	for attempt in queryset:
		attempt.responses.all().delete()
		attempt.status = 'in_progress'
		attempt.submitted_at = None
		attempt.score = 0
		attempt.save(update_fields=['status', 'submitted_at', 'score'])


@admin.register(CBTAttempt)
class CBTAttemptAdmin(admin.ModelAdmin):
	list_display = ('student', 'exam', 'status', 'score', 'submitted_at')
	list_filter = ('status', 'exam__subject')
	actions = [reset_cbt_attempts]
admin.site.register(CBTResponse)
admin.site.register(SubjectResult)
admin.site.register(StudentTermRecord)
admin.site.register(FeeStructure)
admin.site.register(StudentFeeAccount)
admin.site.register(FeePayment)
admin.site.register(SchoolPaymentAccount)
admin.site.register(AdmissionCampaign)
admin.site.register(Applicant)
admin.site.register(Message)
admin.site.register(MessageRecipient)
admin.site.register(StaffSalaryProfile)
admin.site.register(PayrollRun)
admin.site.register(Payslip)
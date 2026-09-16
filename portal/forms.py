from django import forms

from .models import Parent, Student
from .models import Applicant, ClassRoom


class StudentParentForm(forms.Form):
    PARENT_MODE_CHOICES = (
        ('', 'No parent linked'),
        ('new', 'Create New Parent'),
        ('existing', 'Select Existing Parent'),
    )

    parent_mode = forms.ChoiceField(
        choices=PARENT_MODE_CHOICES,
        required=False,
        widget=forms.RadioSelect,
    )
    existing_parent = forms.ModelChoiceField(
        queryset=Parent.objects.none(),
        required=False,
        empty_label='Select an existing parent',
        widget=forms.Select(attrs={'class': 'parent-existing-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['existing_parent'].queryset = Parent.objects.order_by(
            'last_name', 'first_name', 'parent_id'
        )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('parent_mode') == 'existing' and not cleaned_data.get('existing_parent'):
            self.add_error('existing_parent', 'Select an existing parent.')
        return cleaned_data


class ParentStudentLinkForm(forms.Form):
    student = forms.ModelChoiceField(
        queryset=Student.objects.none(),
        empty_label='Select an unlinked student',
        widget=forms.Select(attrs={'class': 'parent-student-select'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = Student.objects.filter(
            status='Student', parent__isnull=True
        ).order_by('last_name', 'first_name')


class ParentChildApplicationForm(forms.ModelForm):
    class Meta:
        model = Applicant
        fields = (
            'first_name', 'last_name', 'other_name', 'date_of_birth', 'sex',
            'nationality', 'religion', 'state_of_origin', 'lga', 'passport',
            'has_disability', 'disability_details', 'school_type',
            'previous_school', 'present_class', 'programme_of_study',
            'intended_class',
        )
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'intended_class': forms.Select(),
            'disability_details': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, campaign=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['intended_class'].queryset = ClassRoom.objects.order_by('section', 'sequence', 'name')
        self.fields['date_of_birth'].required = True
        self.fields['sex'].required = True
        self.fields['other_name'].required = True
        self.fields['intended_class'].required = True

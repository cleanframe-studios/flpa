from django import forms

from .models import Parent, Student


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

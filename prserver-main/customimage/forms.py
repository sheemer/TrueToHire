from django import forms
from  dashboard.models import TestType, SubTest





class TestTypeSubTestForm(forms.Form):
    test_type_name = forms.ModelChoiceField(
        label="Job test is for",
        queryset=TestType.objects.all(),  
        empty_label="Select a test type",
    )
    sub_test_name = forms.CharField(label="Test Identifier", max_length=255)
    is_public = forms.BooleanField(label="Make public to community", required=False)
    details = forms.CharField(label="Test Details", widget=forms.Textarea, required=False)
    instructions = forms.CharField(label="Instructions", widget=forms.Textarea, required=False)
    time_limit = forms.IntegerField(label="Time Limit (minutes)", initial=30, min_value=1)
    instance_type = forms.CharField(initial="t3.micro", widget=forms.HiddenInput())
    ami_id = forms.CharField(required=False, widget=forms.HiddenInput())
    os_type = forms.ChoiceField(
        label="OS Type",
        choices=[('linux', 'Linux'), ('windows', 'Windows')],
        initial='windows'
    )
    script = forms.CharField(label="Shutdown Script", required=False, widget=forms.HiddenInput())
    password = forms.CharField(
        label="Test Room Password",
        max_length=128,
        required=False,
        widget=forms.PasswordInput,
        help_text="Optional password to restrict access to the test room."
    )

    def clean(self):
        cleaned_data = super().clean()
        os_type = cleaned_data.get('os_type')
        instance_type = cleaned_data.get('instance_type')

        # not great maybe call aws to grab lol hard
        if os_type == 'linux':
            cleaned_data['ami_id'] = 'ami-0f88e80871fd81e91'
        elif os_type == 'windows':
            cleaned_data['ami_id'] = 'ami-09cb80360d5069de4'
        else:
            raise forms.ValidationError("Invalid OS type selected.")

        # fuck keep cheap
        valid_instance_types = ['t3.micro', 't3.small', 't3.medium']
        if instance_type not in valid_instance_types:
            raise forms.ValidationError(f"Invalid instance type: {instance_type}")

        return cleaned_data


    def clean_sub_test_name(self):
        name = self.cleaned_data.get('sub_test_name')
        test_type = self.cleaned_data.get('test_type_name')
        if name and test_type:
            if SubTest.objects.filter(name=name, test_type=test_type).exists():
                raise forms.ValidationError("This test type already has a SubTest with this name.")
        return name
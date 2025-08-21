from django import forms
from .models import TestRequest, SubTest

class TestRequestForm(forms.ModelForm):
    class Meta:
        model = TestRequest
        fields = ['title', 'test_type', 'sub_tests', 'password']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Initially set sub_tests to empty until test_type is selected
        self.fields["sub_tests"].queryset = SubTest.objects.none()

        # If an instance or initial data contains test_type, filter SubTests
        if "test_type" in self.data:
            try:
                test_type_id = int(self.data.get("test_type"))
                self.fields["sub_tests"].queryset = SubTest.objects.filter(test_type_id=test_type_id)
            except (ValueError, TypeError):
                pass  # Handle the case where test_type is invalid
# accounts/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator
from accounts.models import CustomUser

class CustomUserCreationForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        required=True,
        help_text="No spaces allowed.",
        validators=[RegexValidator(r'^[\w.@+-]+$', 'Enter a valid username. No spaces allowed.', 'invalid')]
    )
    email = forms.EmailField(max_length=254, required=True, help_text="Enter a valid email address.")
    company_name = forms.CharField(max_length=255, label="Company Name", required=True)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, required=True)
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput, required=True)

    def clean_username(self):
        username = self.cleaned_data['username']
        if CustomUser.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        email = self.cleaned_data['email']
        if CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data
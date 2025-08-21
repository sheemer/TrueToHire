from django import forms
from .models import ImprovementRequest

class ImprovementRequestForm(forms.ModelForm):
    class Meta:
        model = ImprovementRequest
        fields = ['category', 'title', 'description']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Describe the issue'}),
        }

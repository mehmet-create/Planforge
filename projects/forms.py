from django import forms
from .models import Project


class CreateProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = ("name", "description", "status", "budget", "currency")
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Project name"
            }),
            "description": forms.Textarea(attrs={
                "placeholder": "What is this project about?",
                "rows": 4
            }),
            "budget": forms.NumberInput(attrs={
                "placeholder": "e.g. 25000",
                "min": "0",
                "step": "0.01"
            }),
        }

    def clean_budget(self):
        budget = self.cleaned_data.get("budget")
        if budget is not None and budget < 0:
            raise forms.ValidationError("Budget cannot be negative.")
        return budget


class UpdateProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = ("name", "description", "status", "budget", "currency")
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Project name"
            }),
            "description": forms.Textarea(attrs={
                "placeholder": "What is this project about?",
                "rows": 4
            }),
            "budget": forms.NumberInput(attrs={
                "placeholder": "e.g. 25000",
                "min": "0",
                "step": "0.01"
            }),
        }

    def clean_budget(self):
        budget = self.cleaned_data.get("budget")
        if budget is not None and budget < 0:
            raise forms.ValidationError("Budget cannot be negative.")
        return budget
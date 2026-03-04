from django import forms
from .models import Project


class CreateProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = ("name", "description", "status")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Project name"}),
            "description": forms.Textarea(attrs={"placeholder": "What is this project about?", "rows": 4}),
        }


class UpdateProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = ("name", "description", "status")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Project name"}),
            "description": forms.Textarea(attrs={"placeholder": "What is this project about?", "rows": 4}),
        }
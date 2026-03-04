from django import forms
from .models import Membership


class CreateOrganizationForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Organization name"})
    )


class UpdateOrganizationForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Organization name"})
    )


class InviteMemberForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Username"})
    )
    role = forms.ChoiceField(
        choices=[
            ("member", "Member"),
            ("admin",  "Admin"),
        ]
    )


class ChangeMemberRoleForm(forms.Form):
    role = forms.ChoiceField(
        choices=[
            ("member", "Member"),
            ("admin",  "Admin"),
        ]
    )
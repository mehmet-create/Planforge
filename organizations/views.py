# organizations/views.py

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .decorators import org_admin_required, org_member_required, org_owner_required
from .forms import ChangeMemberRoleForm, CreateOrganizationForm, InviteMemberForm, UpdateOrganizationForm
from .models import Membership, Organization
from .schemas import (
    ChangeMemberRoleDTO,
    CreateOrganizationDTO,
    DeleteOrganizationDTO,
    InviteMemberDTO,
    RemoveMemberDTO,
    UpdateOrganizationDTO,
)
from . import services

logger = logging.getLogger(__name__)


# Organization list

@login_required
def org_list(request):
    """
    Show all organizations the user belongs to.
    This is also the page they land on if they have no active org.
    """
    orgs = services.get_user_organizations(request.user.id)
    return render(request, "organizations/list.html", {"orgs": orgs})


# Create organization

@login_required
@require_http_methods(["GET", "POST"])
def org_create(request):
    form = CreateOrganizationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            dto = CreateOrganizationDTO(
                name=form.cleaned_data["name"],
                created_by_id=request.user.id,
            )
            org = services.create_organization(dto)

            # Set the new org as active immediately
            services.set_active_organization(request, org.id)

            messages.success(request, f"'{org.name}' created successfully.")
            return redirect("organizations:settings", org_slug=org.slug)

        except (services.ServiceError, ValueError) as e:
            messages.error(request, str(e))

    return render(request, "organizations/create.html", {"form": form})


# Switch active organization

@login_required
@require_POST
def org_switch(request, org_slug):
    """
    Switch the user's active organization.
    POST only — switching org changes session state, should not be a GET.
    """
    org = get_object_or_404(Organization, slug=org_slug)

    try:
        services.set_active_organization(request, org.id)
        messages.success(request, f"Switched to '{org.name}'.")
    except services.PermissionDenied as e:
        messages.error(request, str(e))

    # Go back to wherever they were, fall back to dashboard
    next_url = request.POST.get("next", "")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("dashboard")


# Organization settings

@login_required
@org_member_required
def org_settings(request, org_slug):
    """
    Organization settings page.
    Shows org info, member list, and actions depending on user's role.
    """
    members = services.get_organization_members(request.active_org.id)
    form    = UpdateOrganizationForm(initial={"name": request.active_org.name})

    return render(request, "organizations/settings.html", {
        "org":        request.active_org,
        "membership": request.membership,
        "members":    members,
        "form":       form,
    })


# Update organization name

@login_required
@org_admin_required
@require_POST
def org_update(request, org_slug):
    form = UpdateOrganizationForm(request.POST)

    if form.is_valid():
        try:
            dto = UpdateOrganizationDTO(
                organization_id=request.active_org.id,
                acting_user_id=request.user.id,
                name=form.cleaned_data["name"],
            )
            org = services.update_organization(dto)
            messages.success(request, "Organization name updated.")
            return redirect("organizations:settings", org_slug=org.slug)

        except (services.ServiceError, services.PermissionDenied, ValueError) as e:
            messages.error(request, str(e))

    else:
        messages.error(request, "Please correct the errors below.")

    return redirect("organizations:settings", org_slug=org_slug)


# Invite member

@login_required
@org_admin_required
@require_POST
def org_invite_member(request, org_slug):
    form = InviteMemberForm(request.POST)

    if form.is_valid():
        try:
            dto = InviteMemberDTO(
                organization_id=request.active_org.id,
                acting_user_id=request.user.id,
                target_username=form.cleaned_data["username"],
                role=form.cleaned_data["role"],
            )
            membership = services.invite_member(dto)
            messages.success(
                request,
                f"{membership.user.username} added as {membership.role}."
            )

        except (services.ServiceError, services.PermissionDenied, ValueError) as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Please correct the errors below.")

    return redirect("organizations:settings", org_slug=org_slug)


# Remove member

@login_required
@require_POST
def org_remove_member(request, org_slug, user_id):
    org = get_object_or_404(Organization, slug=org_slug)

    try:
        dto = RemoveMemberDTO(
            organization_id=org.id,
            acting_user_id=request.user.id,
            target_user_id=user_id,
        )
        services.remove_member(dto)

        # int() because user_id from the URL is a string
        if int(user_id) == request.user.id:
            request.session.pop("active_org_id", None)
            messages.success(request, f"You have left '{org.name}'.")
            return redirect("organizations:list")

        messages.success(request, "Member removed.")

    except (services.ServiceError, services.PermissionDenied) as e:
        messages.error(request, str(e))

    return redirect("organizations:settings", org_slug=org_slug)

# Change member role 

@login_required
@org_owner_required
@require_POST
def org_change_member_role(request, org_slug, user_id):
    form = ChangeMemberRoleForm(request.POST)

    if form.is_valid():
        try:
            dto = ChangeMemberRoleDTO(
                organization_id=request.active_org.id,
                acting_user_id=request.user.id,
                target_user_id=user_id,
                new_role=form.cleaned_data["role"],
            )
            services.change_member_role(dto)
            messages.success(request, "Role updated.")

        except (services.ServiceError, services.PermissionDenied, ValueError) as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Invalid role.")

    return redirect("organizations:settings", org_slug=org_slug)


# Delete organization

@login_required
@org_owner_required
@require_POST
def org_delete(request, org_slug):
    try:
        dto = DeleteOrganizationDTO(
            organization_id=request.active_org.id,
            acting_user_id=request.user.id,
        )
        org_name = request.active_org.name
        services.delete_organization(dto)

        # Clear org from session since it no longer exists
        request.session.pop("active_org_id", None)
        messages.success(request, f"'{org_name}' has been permanently deleted.")

    except (services.ServiceError, services.PermissionDenied) as e:
        messages.error(request, str(e))
        return redirect("organizations:settings", org_slug=org_slug)

    return redirect("organizations:list")
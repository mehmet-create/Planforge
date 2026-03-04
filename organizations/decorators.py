# Reusable view decorators for organization-level access control.

# Usage example:
#   @login_required
#   @org_member_required
#   def some_view(request, org_slug):


from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .services import get_active_organization, get_user_membership, ServiceError


def org_member_required(view_func):
    """
    Ensures the user is a member of the active organization.
    If not, redirects to the organization list.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        active_org = get_active_organization(request)

        if not active_org:
            messages.warning(request, "Please select or create an organization first.")
            return redirect("organizations:list")

        membership = get_user_membership(request.user.id, active_org.id)
        if not membership:
            messages.error(request, "You are not a member of this organization.")
            return redirect("organizations:list")

        # Attach to request so the view can use it without another DB query
        request.active_org  = active_org
        request.membership  = membership
        return view_func(request, *args, **kwargs)

    return wrapper


def org_admin_required(view_func):
    """
    Ensures the user is an admin or owner of the active organization.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        active_org = get_active_organization(request)

        if not active_org:
            messages.warning(request, "Please select or create an organization first.")
            return redirect("organizations:list")

        membership = get_user_membership(request.user.id, active_org.id)
        if not membership or not membership.is_admin_or_owner:
            messages.error(request, "You need admin or owner access for this action.")
            return redirect("organizations:list")

        request.active_org = active_org
        request.membership = membership
        return view_func(request, *args, **kwargs)

    return wrapper


def org_owner_required(view_func):
    """
    Ensures the user is the owner of the active organization.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        active_org = get_active_organization(request)

        if not active_org:
            messages.warning(request, "Please select or create an organization first.")
            return redirect("organizations:list")

        membership = get_user_membership(request.user.id, active_org.id)
        if not membership or not membership.is_owner:
            messages.error(request, "Only the organization owner can do this.")
            return redirect("organizations:list")

        request.active_org = active_org
        request.membership = membership
        return view_func(request, *args, **kwargs)

    return wrapper
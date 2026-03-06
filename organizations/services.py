# All business logic for organizations and memberships.

# Rules:
# - Every function takes a DTO or simple primitives, never a request object
# - Role checks happen here, not in views
# - Multi-step DB operations use transaction.atomic()
# - Raise ServiceError on failure — never return None silently

import logging
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Organization, Membership

logger = logging.getLogger(__name__)
User   = get_user_model()


# Exceptions

class ServiceError(Exception):
    """Business logic failure — safe to show message to the user."""
    pass


class PermissionDenied(ServiceError):
    """The acting user does not have permission for this action."""
    pass


# Internal helpers

def _get_membership(user_id: int, organization_id: int) -> Membership:
    """
    Fetch a membership or raise ServiceError.
    Used internally to avoid repeating the same try/except everywhere.
    """
    try:
        return Membership.objects.get(
            user_id=user_id,
            organization_id=organization_id
        )
    except Membership.DoesNotExist:
        raise ServiceError("You are not a member of this organization.")


def _require_admin_or_owner(user_id: int, organization_id: int) -> Membership:
    """
    Fetch membership and confirm the user is admin or owner.
    Raises PermissionDenied if they're not.
    Returns the membership if they are.
    """
    membership = _get_membership(user_id, organization_id)
    if not membership.is_admin_or_owner:
        raise PermissionDenied("You do not have permission to perform this action.")
    return membership


def _require_owner(user_id: int, organization_id: int) -> Membership:
    """
    Fetch membership and confirm the user is the owner.
    Raises PermissionDenied if they're not.
    """
    membership = _get_membership(user_id, organization_id)
    if not membership.is_owner:
        raise PermissionDenied("Only the organization owner can perform this action.")
    return membership


# Organization CRUD 

def create_organization(dto):
    """
    Create a new organization and automatically make the creator the owner.

    Both the organization and the owner membership are created together
    in one transaction — if either fails, neither is saved.
    """
    with transaction.atomic():
        try:
            creator = User.objects.get(pk=dto.created_by_id)
        except User.DoesNotExist:
            raise ServiceError("User not found.")

        org = Organization.objects.create(
            name=dto.name,
            created_by=creator
        )

        # Automatically give the creator owner-level membership
        Membership.objects.create(
            user=creator,
            organization=org,
            role=Membership.Role.OWNER,
            invited_by=None
        )   

        logger.info("Organization '%s' created by user %s", org.name, creator.username)
        return org



def update_organization(dto):
    """
    Update organization name. Only owners and admins can do this.
    """
    _require_admin_or_owner(dto.acting_user_id, dto.organization_id)

    try:
        org = Organization.objects.get(pk=dto.organization_id)
    except Organization.DoesNotExist:
        raise ServiceError("Organization not found.")

    org.name = dto.name
    # Slug is intentionally NOT regenerated — it was set once at creation.
    # Changing the slug would break all existing bookmarks and shared links.
    org.save()

    return org


def delete_organization(dto):
    """
    Permanently delete an organization. Only the owner can do this.
    Deleting an org cascades to all its memberships and projects.
    """
    _require_owner(dto.acting_user_id, dto.organization_id)

    try:
        org = Organization.objects.get(pk=dto.organization_id)
    except Organization.DoesNotExist:
        raise ServiceError("Organization not found.")

    org_name = org.name
    org.delete()
    logger.info("Organization '%s' deleted by user %s", org_name, dto.acting_user_id)
    return True


# Membership queries 

def get_user_organizations(user_id: int):
    """
    Return all organizations the user is a member of.
    Ordered by org name.
    """
    return Organization.objects.filter(
        memberships__user_id=user_id
    ).order_by("name")


def get_user_membership(user_id: int, organization_id: int):
    """
    Return the user's membership in a specific org, or None.
    Use this when you need the role — e.g. to decide what UI to show.
    """
    try:
        return Membership.objects.get(
            user_id=user_id,
            organization_id=organization_id
        )
    except Membership.DoesNotExist:
        return None


def get_organization_members(organization_id: int):
    """
    Return all memberships for an organization, with user data pre-fetched.
    select_related('user') avoids N+1 queries when rendering a member list.
    """
    return (
        Membership.objects
        .filter(organization_id=organization_id)
        .select_related("user")
        .order_by("joined_at")
    )


# Member management

def invite_member(dto):
    acting_membership = _require_admin_or_owner(dto.acting_user_id, dto.organization_id)

    try:
        target_user = User.objects.get(username__iexact=dto.target_username, is_active=True)
    except User.DoesNotExist:
        raise ServiceError(f"No active user found with username '{dto.target_username}'.")

    if Membership.objects.filter(
        user=target_user,
        organization_id=dto.organization_id
    ).exists():
        raise ServiceError(f"{target_user.username} is already a member of this organization.")

    try:
        acting_user = User.objects.get(pk=dto.acting_user_id)
    except User.DoesNotExist:
        acting_user = None

    membership = Membership.objects.create(
        user=target_user,
        organization_id=dto.organization_id,
        role=dto.role,
        invited_by=acting_user    # ← record who sent the invite
    )

    logger.info(
        "User %s added to org %s as %s by user %s",
        target_user.username, dto.organization_id, dto.role, dto.acting_user_id
    )
    return membership

def remove_member(dto):
    """
    Remove a member from an organization by their membership UUID.
    """
    acting_membership = _get_membership(dto.acting_user_id, dto.organization_id)

    try:
        target_membership = Membership.objects.get(
            uuid=dto.target_membership_uuid,
            organization_id=dto.organization_id,
        )
    except Membership.DoesNotExist:
        raise ServiceError("That membership does not exist.")

    # Owners cannot be removed
    if target_membership.is_owner:
        raise PermissionDenied("The organization owner cannot be removed.")

    # Admins can only be removed by the owner
    if target_membership.is_admin and not acting_membership.is_owner:
        raise PermissionDenied("Only the owner can remove an admin.")

    # Regular members can remove themselves
    is_self = target_membership.user_id == dto.acting_user_id
    if not is_self and not acting_membership.is_admin_or_owner:
        raise PermissionDenied("You don't have permission to remove this member.")

    target_membership.delete()
    return target_membership.user_id   # return so view can detect self-removal


def change_member_role(dto):
    """
    Change a member's role within an organization.
    Only the owner can do this.
    """
    _require_owner(dto.acting_user_id, dto.organization_id)

    try:
        target_membership = Membership.objects.get(
            uuid=dto.target_membership_uuid,
            organization_id=dto.organization_id,
        )
    except Membership.DoesNotExist:
        raise ServiceError("That membership does not exist.")

    if target_membership.user_id == dto.acting_user_id:
        raise PermissionDenied("You cannot change your own role.")

    if target_membership.is_owner:
        raise PermissionDenied("The owner's role cannot be changed.")

    target_membership.role = dto.new_role
    target_membership.save()
    return target_membership


# Organization switching 
# The "active organization" is stored in the session.
# This is what allows a user to switch between orgs without losing context.

def set_active_organization(request, organization_id: int):
    """
    Set the active organization in the session.
    Verifies the user is actually a member before allowing the switch.
    """
    membership = get_user_membership(request.user.id, organization_id)
    if not membership:
        raise PermissionDenied("You are not a member of that organization.")

    request.session["active_org_id"] = organization_id
    return membership.organization


def get_active_organization(request):
    """
    Return the currently active Organization for this session, or None.
    Called by the context processor so every template has access to it.
    """
    if not request.user.is_authenticated:
        return None

    org_id = request.session.get("active_org_id")

    if not org_id:
        # No org set in session — default to the first one the user belongs to
        first_org = get_user_organizations(request.user.id).first()
        if first_org:
            request.session["active_org_id"] = first_org.id
        return first_org

    # Verify the user still belongs to the stored org
    # (they could have been removed since last session)
    membership = get_user_membership(request.user.id, org_id)
    if not membership:
        # They no longer belong — clear the stale session value
        request.session.pop("active_org_id", None)
        # Fall back to first available org
        first_org = get_user_organizations(request.user.id).first()
        if first_org:
            request.session["active_org_id"] = first_org.id
        return first_org

    return membership.organization
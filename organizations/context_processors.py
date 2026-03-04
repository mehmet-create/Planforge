# A context processor runs on every request and injects variables
# into every template automatically — no need to pass them manually from each view.

# This one makes two things available in every template:
#   {{ active_org }}     — the organization the user is currently working in
#   {{ user_orgs }}      — all organizations the user belongs to (for a switcher)

from .services import get_active_organization, get_user_organizations


def organization_context(request):
    if not request.user.is_authenticated:
        return {
            "active_org": None,
            "user_orgs":  [],
        }

    # get_active_organization handles session caching and membership validation
    active_org = get_active_organization(request)

    # Only fetch all orgs if we need to show the switcher
    # We fetch here so every template can render the org switcher in the navbar
    user_orgs = get_user_organizations(request.user.id)

    return {
        "active_org": active_org,
        "user_orgs":  user_orgs,
    }
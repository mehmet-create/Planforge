from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
import logging
from organizations.services import get_active_organization
from projects.models import Project
from blueprints.models import Blueprint
from organizations.services import get_user_membership

logger = logging.getLogger(__name__)


def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "home.html")


@login_required
def dashboard(request):
    active_org = get_active_organization(request)

    if not active_org:
        return redirect("organizations:create")

    
    membership = get_user_membership(request.user.id, active_org.id)

    recent_projects = Project.objects.filter(
        organization=active_org
    ).order_by("-created_at")[:5]

    all_projects_count = Project.objects.filter(
        organization=active_org
    ).count()

    members_count = active_org.memberships.count()

    recent_blueprints = Blueprint.objects.filter(
        organization=active_org,
        is_complete=True,
    ).select_related("project", "created_by").order_by("-created_at")[:5]

    blueprints_count = Blueprint.objects.filter(
        organization=active_org,
        is_complete=True,
    ).count()

    return render(request, "dashboard.html", {
        "active_org":         active_org,
        "membership":         membership,
        "recent_projects":    recent_projects,
        "all_projects_count": all_projects_count,
        "members_count":      members_count,
        "recent_blueprints":  recent_blueprints,
        "blueprints_count":   blueprints_count,
    })
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from organizations.decorators import org_admin_required, org_member_required
from projects.forms import CreateProjectForm, UpdateProjectForm
from projects.models import Project

logger = logging.getLogger(__name__)


# Project list

@login_required
@org_member_required
def project_list(request):
    """
    List all projects in the active organization.
    org_member_required attaches request.active_org and request.membership.
    """
    projects = Project.objects.filter(
        organization=request.active_org
    ).order_by("-created_at")

    return render(request, "projects/list.html", {
        "projects": projects,
        "org": request.active_org,
        "membership": request.membership,
    })


# Project create

@login_required
@org_admin_required
@require_http_methods(["GET", "POST"])
def project_create(request):
    """
    Any member can create a project inside the active organization.
    """
    form = CreateProjectForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        project = form.save(commit=False)
        project.organization = request.active_org
        project.created_by = request.user
        project.save()

        messages.success(request, f"'{project.name}' created.")
        return redirect("projects:detail", project_uuid=project.uuid)

    return render(request, "projects/create.html", {
        "form": form,
        "org": request.active_org,
    })


# Project detail

@login_required
@org_member_required
def project_detail(request, project_uuid):
    project = get_object_or_404(
        Project,
        uuid=project_uuid,
        organization=request.active_org
    )
    # Pass form so the edit modal's status dropdown works
    form = UpdateProjectForm(instance=project)

    return render(request, "projects/detail.html", {
        "project":    project,
        "org":        request.active_org,
        "membership": request.membership,
        "form":       form,
    })

# Project edit

@login_required
@org_admin_required
@require_http_methods(["GET", "POST"])
def project_edit(request, project_uuid):
    """
    Any member can edit a project for now.
    We can restrict this to admin/owner in Phase 6 if needed.
    """
    project = get_object_or_404(
        Project,
        uuid=project_uuid,
        organization=request.active_org
    )

    form = UpdateProjectForm(request.POST or None, instance=project)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"'{project.name}' updated.")
        return redirect("projects:detail", project_uuid=project.uuid)

    return render(request, "projects/edit.html", {
        "form":    form,
        "project": project,
        "org":     request.active_org,
    })


# Project delete

@login_required
@org_admin_required
@require_POST
def project_delete(request, project_uuid):
    """
    Only admins and owners can delete projects.
    """
    project = get_object_or_404(
        Project,
        uuid=project_uuid,
        organization=request.active_org
    )

    project_name = project.name
    project.delete()

    messages.success(request, f"'{project_name}' deleted.")
    return redirect("projects:list")
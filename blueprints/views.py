from django.shortcuts import render, get_object_or_404, redirect
import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_http_methods
from organizations.decorators import org_member_required, org_admin_required
from projects.models import Project
from . import services
from .models import Blueprint
from .schemas import DeleteBlueprintDTO, GenerateBlueprintDTO
# Create your views here.


logger = logging.getLogger(__name__)


@login_required
@org_member_required
@require_http_methods(["GET", "POST"])
def blueprint_generate(request, project_id):
    """
    GET  — show the generate form for this project
    POST — call Gemini, save result, redirect to the result page
    """

    project = get_object_or_404(
        Project,
        id=project_id,
        organization=request.active_org
    )

    if not request.membership.is_admin_or_owner:
        messages.error(request, "You need admin or owner access for this action.")
        return redirect("projects:detail", project_id=project.id)
    
    # Past blueprints for this project (shown in sidebar)
    past_blueprints = services.get_project_blueprints(
        project.id, request.active_org.id
    )

    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()

        if not prompt:
            messages.error(request, "Please describe your project before generating.")
            return render(request, "blueprints/generate.html", {
                "project":         project,
                "past_blueprints": past_blueprints,
                "prompt":          prompt,
            })

        try:
            dto = GenerateBlueprintDTO(
                project_id=project.id,
                organization_id=request.active_org.id,
                acting_user_id=request.user.id,
                prompt=prompt,
            )
            blueprint = services.generate_blueprint(dto)
            messages.success(request, "Blueprint generated successfully.")
            return redirect("blueprints:detail", blueprint_id=blueprint.id)

        except (services.ServiceError, ValueError) as e:
            messages.error(request, str(e))
            return render(request, "blueprints/generate.html", {
                "project":         project,
                "past_blueprints": past_blueprints,
                "prompt":          prompt,
            })

    return render(request, "blueprints/generate.html", {
        "project":         project,
        "past_blueprints": past_blueprints,
        "prompt":          "",
    })


@login_required
@org_member_required
def blueprint_detail(request, blueprint_uuid):
    blueprint = get_object_or_404(
        Blueprint,
        uuid=blueprint_uuid,
        organization=request.active_org
    )
    return render(request, "blueprints/detail.html", {
        "blueprint": blueprint,
        "project":   blueprint.project,
        "result":    blueprint.result,
    })

@login_required
@org_member_required
def blueprint_list(request):
    """
    All blueprints for the active org, grouped by project.
    """
    blueprints = services.get_org_blueprints(request.active_org.id)

    return render(request, "blueprints/list.html", {
        "blueprints": blueprints,
    })


@login_required
@org_member_required
@require_POST
def blueprint_delete(request, blueprint_uuid):
    try:
        dto = DeleteBlueprintDTO(
            blueprint_uuid=blueprint_uuid,
            acting_user_id=request.user.id,
            organization_id=request.active_org.id,
        )
        services.delete_blueprint(dto)
        messages.success(request, "Blueprint deleted.")
    except (services.ServiceError, services.PermissionDenied) as e:
        messages.error(request, str(e))
    return redirect("blueprints:list")

@login_required
@org_member_required
@require_POST
def blueprint_export(request, blueprint_uuid):
    try:
        project = services.export_blueprint_to_project(
            blueprint_uuid=blueprint_uuid,
            organization_id=request.active_org.id,
            acting_user_id=request.user.id,
        )
        messages.success(request, f"Blueprint exported to '{project.name}'.")
        return redirect("projects:detail", project_id=project.id)
    except (services.ServiceError, services.PermissionDenied) as e:
        messages.error(request, str(e))
        return redirect("blueprints:detail", blueprint_uuid=blueprint_uuid)
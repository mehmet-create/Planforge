import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from organizations.decorators import org_admin_required, org_member_required
from projects.models import Project
from . import services
from .models import Blueprint
from .schemas import DeleteBlueprintDTO, GenerateBlueprintDTO

logger = logging.getLogger(__name__)


@login_required
@org_admin_required          
@require_http_methods(["GET", "POST"])
def blueprint_generate(request, project_uuid):
    project = get_object_or_404(
        Project,
        uuid=project_uuid,
        organization=request.active_org
    )

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
            return redirect("blueprints:detail", blueprint_uuid=blueprint.uuid)

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
        "blueprint":  blueprint,
        "project":    blueprint.project,
        "result":     blueprint.result,
        "membership": request.membership,
    })


@login_required
@org_member_required                   
def blueprint_list(request):
    blueprints = services.get_org_blueprints(request.active_org.id)
    return render(request, "blueprints/list.html", {
        "blueprints": blueprints,
    })


@login_required
@org_admin_required                    
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
@org_admin_required            
@require_POST
def blueprint_export(request, blueprint_uuid):
    try:
        project = services.export_blueprint_to_project(
            blueprint_uuid=blueprint_uuid,
            organization_id=request.active_org.id,
            acting_user_id=request.user.id,
        )
        messages.success(request, f"Blueprint exported to '{project.name}'.")
        return redirect("projects:detail", project_uuid=project.uuid)
    except (services.ServiceError, services.PermissionDenied) as e:
        messages.error(request, str(e))
        return redirect("blueprints:detail", blueprint_uuid=blueprint_uuid)
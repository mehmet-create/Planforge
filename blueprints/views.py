import logging
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from core.ratelimit import check_ratelimit, RateLimitError
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
        # Per-user rate limit: 5 per minute
        try:
            check_ratelimit(f"blueprint_gen_{request.user.id}", limit=5, period=60)
        except RateLimitError:
            messages.error(request, "You're generating blueprints too quickly. Please wait a moment.")
            return render(request, "blueprints/generate.html", {
                "project":         project,
                "past_blueprints": past_blueprints,
                "prompt":          request.POST.get("prompt", "").strip(),
            })

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
            # Fast synchronous part: quota check + DB insert only
            blueprint = services.create_blueprint_record(dto)

        except (services.ServiceError, ValueError) as e:
            messages.error(request, str(e))
            return render(request, "blueprints/generate.html", {
                "project":         project,
                "past_blueprints": past_blueprints,
                "prompt":          prompt,
            })

        # Slow async part: run the AI call on a daemon thread.
        # The WSGI worker returns to the client immediately — the thread runs
        # in the background and updates the Blueprint row when done.
        # The pending page polls /status/ every 2 s to detect completion.
        #
        # Tradeoff vs Celery: no automatic retry and no persistence if the
        # process restarts mid-generation (rare on Render). Acceptable for a
        # 512 MB instance where a Celery worker process would cost ~120 MB.
        # To upgrade later: replace these two lines with:
        #   from .tasks import generate_blueprint_task
        #   generate_blueprint_task.delay(blueprint.id)
        import threading
        t = threading.Thread(
            target=services.run_blueprint_generation,
            args=(blueprint.id,),
            daemon=True,
            name=f"blueprint-{blueprint.uuid}",
        )
        t.start()

        return redirect("blueprints:pending", blueprint_uuid=blueprint.uuid)

    return render(request, "blueprints/generate.html", {
        "project":         project,
        "past_blueprints": past_blueprints,
        "prompt":          "",
    })


@login_required
@org_member_required
def blueprint_pending(request, blueprint_uuid):
    """
    Waiting room. Two layers:
    - No-JS fallback: <meta http-equiv="refresh" content="3"> reloads the page;
      this view redirects to detail once is_complete=True.
    - JS upgrade: EventSource connects to blueprint_stream, which pushes a
      'complete' or 'failed' event the instant the thread finishes — no waiting
      for the next meta-refresh tick.
    """
    blueprint = get_object_or_404(
        Blueprint,
        uuid=blueprint_uuid,
        organization=request.active_org
    )

    if blueprint.is_complete:
        return redirect("blueprints:detail", blueprint_uuid=blueprint.uuid)

    return render(request, "blueprints/pending.html", {
        "blueprint": blueprint,
        "project":   blueprint.project,
    })


@login_required
@org_member_required
def blueprint_stream(request, blueprint_uuid):
    """
    Server-Sent Events endpoint. Holds an open HTTP connection and pushes
    one event every 2 seconds until the blueprint is complete or failed.

    The browser's native EventSource API handles reconnection automatically
    if the connection drops. No library needed on either end.

    Used only when JS is available — the meta refresh fallback in pending.html
    means this view is never critical-path for no-JS browsers.
    """
    blueprint = get_object_or_404(
        Blueprint,
        uuid=blueprint_uuid,
        organization=request.active_org
    )

    detail_url = f"/blueprints/{blueprint_uuid}/"

    def event_stream():
        # Send a comment immediately so the browser knows the connection is live.
        # Some proxies buffer SSE until the first byte arrives.
        yield ": connected\n\n"

        for _ in range(90):          # max ~3 minutes (90 × 2 s)
            # Re-fetch from DB on every tick — the daemon thread updates this row
            bp = Blueprint.objects.get(pk=blueprint.pk)

            if bp.is_complete:
                yield f"event: complete\ndata: {detail_url}\n\n"
                return

            if bp.error:
                # JSON-encode the error so quotes don't break the SSE format
                import json
                yield f"event: failed\ndata: {json.dumps(bp.error)}\n\n"
                return

            # Still running — send a heartbeat so the connection stays alive
            # through proxies that close idle connections after 30–60 s.
            yield ": heartbeat\n\n"
            time.sleep(2)

        # Timed out on the server side — tell the client to stop waiting
        yield "event: timeout\ndata: \n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"   # disable Nginx response buffering for SSE
    return response



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
    return render(request, "blueprints/list.html", {"blueprints": blueprints})


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
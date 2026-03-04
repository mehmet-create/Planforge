import json
import logging
import os

from django.contrib.auth import get_user_model
from google import genai
from projects.models import Project
from .models import Blueprint, BlueprintMessage

logger = logging.getLogger(__name__)
User   = get_user_model()


class ServiceError(Exception):
    pass


class PermissionDenied(ServiceError):
    pass


# ── Gemini ───────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> str:
    """
    Try Gemini first. If it fails (quota, rate limit, unavailable),
    fall back to Groq automatically.
    """
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    groq_key   = os.getenv("GROQ_API_KEY", "")

    if not gemini_key and not groq_key:
        raise ServiceError(
            "No AI API key configured. Add GEMINI_API_KEY or GROQ_API_KEY to your .env file."
        )

    # Try Gemini first
    if gemini_key:
        try:
            from google import genai
            client   = genai.Client(api_key=gemini_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            logger.info("Blueprint generated via Gemini")
            return response.text.strip()

        except Exception as e:
            logger.warning(
                "Gemini failed (%s) — falling back to Groq.", e
            )

    # Fall back to Groq
    if not groq_key:
        raise ServiceError(
            "Gemini is unavailable and no GROQ_API_KEY is set. "
            "Add GROQ_API_KEY to your .env file as a fallback."
        )

    try:
        from groq import Groq
        client = Groq(api_key=groq_key)
        chat   = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        logger.info("Blueprint generated via Groq (Gemini fallback)")
        return chat.choices[0].message.content.strip()

    except Exception as e:
        logger.exception("Groq also failed: %s", e)
        raise ServiceError(f"Both Gemini and Groq failed: {e}")


def _build_system_prompt(project: Project) -> str:
    """
    Build the context block that goes before the user's prompt.
    Tells Gemini exactly what format to return.
    """
    budget_line = (
        f"Budget: {project.budget_display}"
        if project.budget
        else "Budget: Not specified"
    )

    return f"""You are an expert project planning assistant for Planforge, a B2B project management tool.

The user wants a detailed blueprint for their project.

PROJECT CONTEXT:
- Name: {project.name}
- Description: {project.description or 'Not provided'}
- {budget_line}
- Status: {project.get_status_display()}

Your response MUST be valid JSON only — no markdown, no backticks, no explanation outside the JSON.

Return exactly this structure:
{{
  "overview": "2-3 sentence summary of the project and approach",
  "cost_breakdown": [
    {{
      "item": "Category name (e.g. Frontend Development)",
      "min": 5000,
      "max": 8000,
      "notes": "Brief explanation of what's included"
    }}
  ],
  "timeline": [
    {{
      "phase": "Phase name (e.g. Discovery & Planning)",
      "duration": "e.g. 2 weeks",
      "description": "What happens in this phase"
    }}
  ],
  "recommendations": [
    "Specific actionable recommendation 1",
    "Specific actionable recommendation 2",
    "Specific actionable recommendation 3"
  ],
  "total_min": 15000,
  "total_max": 25000
}}

Rules:
- total_min and total_max must be integers (sum of all cost_breakdown mins/maxes)
- If no budget is specified, estimate realistic market rates
- If a budget IS specified, work within it and flag if it is insufficient
- Be specific — generic advice is not useful
- cost_breakdown should have 4-8 items
- timeline should have 3-6 phases
- recommendations should have 3-5 items
"""


def generate_blueprint(dto) -> Blueprint:
    try:
        project = Project.objects.select_related("organization").get(
            pk=dto.project_id,
            organization_id=dto.organization_id
        )
    except Project.DoesNotExist:
        raise ServiceError("Project not found.")

    try:
        acting_user = User.objects.get(pk=dto.acting_user_id)
    except User.DoesNotExist:
        raise ServiceError("User not found.")

    blueprint = Blueprint.objects.create(
        project=project,
        organization=project.organization,
        created_by=acting_user,
        prompt=dto.prompt,
        is_complete=False,
    )

    BlueprintMessage.objects.create(
        blueprint=blueprint,
        role=BlueprintMessage.Role.USER,
        content=dto.prompt,
    )

    try:
        system     = _build_system_prompt(project)
        full_prompt = f"{system}\n\nUser's request:\n{dto.prompt}"

        raw_text = _call_gemini(full_prompt)

        # Strip markdown fences if Gemini adds them anyway
        if raw_text.startswith("```"):
            lines    = raw_text.split("\n")
            lines    = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        result = json.loads(raw_text)

        BlueprintMessage.objects.create(
            blueprint=blueprint,
            role=BlueprintMessage.Role.ASSISTANT,
            content=raw_text,
        )

        blueprint.result      = result
        blueprint.is_complete = True
        blueprint.save()

        logger.info(
            "Blueprint generated for project %s by user %s",
            project.name, acting_user.username
        )

    except json.JSONDecodeError as e:
        logger.error("Gemini returned invalid JSON for project %s: %s", project.name, e)
        blueprint.error = f"Gemini returned invalid JSON: {e}"
        blueprint.save()
        raise ServiceError("The AI returned an unexpected response. Please try again.")

    except ServiceError:
        raise

    except Exception as e:
        logger.exception("Gemini call failed for project %s: %s", project.name, e)
        blueprint.error = str(e)
        blueprint.save()
        raise ServiceError(f"Generation failed: {e}")

    return blueprint


def get_project_blueprints(project_id: int, organization_id: int):
    return Blueprint.objects.filter(
        project_id=project_id,
        organization_id=organization_id,
        is_complete=True,
    ).select_related("created_by")


def get_org_blueprints(organization_id: int):
    return Blueprint.objects.filter(
        organization_id=organization_id,
        is_complete=True,
    ).select_related("project", "created_by")


def get_blueprint(blueprint_uuid, organization_id: int) -> Blueprint:
    try:
        return Blueprint.objects.select_related(
            "project", "created_by"
        ).get(uuid=blueprint_uuid, organization_id=organization_id)
    except Blueprint.DoesNotExist:
        raise ServiceError("Blueprint not found.")


def delete_blueprint(dto) -> None:
    try:
        blueprint = Blueprint.objects.get(
            uuid=dto.blueprint_uuid,
            organization_id=dto.organization_id,
        )
    except Blueprint.DoesNotExist:
        raise ServiceError("Blueprint not found.")

    if blueprint.created_by_id != dto.acting_user_id:
        raise PermissionDenied("You can only delete your own blueprints.")

    blueprint.delete()


def export_blueprint_to_project(blueprint_uuid: int, organization_id: int, acting_user_id: int) -> Project:
    """
    Apply a blueprint's result back onto its project —
    updates description (if empty) and budget (if not already set).
    Returns the updated project.
    """
    blueprint = get_blueprint(blueprint_uuid, organization_id)
    project   = blueprint.project

    changed = False

    # Only fill description if it's currently empty
    if not project.description and blueprint.result.get("overview"):
        project.description = blueprint.result["overview"]
        changed = True

    # Only fill budget if not already set
    if project.budget is None and blueprint.result.get("total_min"):
        project.budget = blueprint.result["total_min"]
        changed = True

    if changed:
        project.save()
        logger.info(
            "Blueprint %s exported to project %s by user %s",
            blueprint_uuid, project.name, acting_user_id
        )

    return project


def cleanup_failed_blueprints(organization_id: int) -> int:
    """
    Delete incomplete/failed blueprint records older than 1 hour.
    Returns how many were deleted.
    """
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(hours=1)
    qs = Blueprint.objects.filter(
        organization_id=organization_id,
        is_complete=False,
        created_at__lt=cutoff,
    )
    count, _ = qs.delete()
    if count:
        logger.info("Cleaned up %s failed blueprints for org %s", count, organization_id)
    return count    